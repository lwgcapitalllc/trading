/**
 * The broker-account form, and the helpers the Bots page reads accounts through.
 *
 * 🔴 **This file was `AccountsTab.tsx`, and that tab had not rendered since the 2026-09-05 rebuild**
 * (one list plus two drawers). Its 1,300 unreachable lines went on 2026-09-11; only what the
 * account panel, the Sync VPS drawer and the page itself import is left. Anything added to a
 * component nothing renders is dead on arrival — rule 9 in the frontend.
 *
 * 🔴 **THREE CARDS, AND THE FIRST IS NOT YOURS TO TYPE (2026-09-13).** Aaron: *"some of these fields
 * I should NOT be able to edit — they are read directly off the VPS mt5 instance … separate mt5
 * level info from telegram channel stuff."* The form was twelve look-alike boxes with a paragraph
 * under each, and the login, server, broker, demo-or-live, terminal and symbol ending were all boxes
 * you could type over — demo-or-live included, the one field that switches a live account's
 * warnings and its channel rule off. Now:
 *
 * - **MT5 account** — the terminal's facts as TEXT, locked, with how they change (Sync VPS). The
 *   password sits here because it is the MT5 login's. Two gaps stay fillable because the box may
 *   not have filled them — a terminal nobody recorded (the VPS is asked first) and a symbol ending
 *   nobody measured — each behind its own "by hand" link, never an open box.
 * - **In this app** — what only this app knows: the nickname, the cost model (a list of the
 *   measured profiles, so a name the server would refuse cannot be typed) and the tier.
 * - **Telegram** — the three channels, each with its Send test.
 *
 * ⚠ **Login, server and demo-or-live are NOT repeated in the card** — the panel's heading shows them
 * the whole time (*Say it once*). The by-hand form has no such heading, so it asks for them.
 * ⚠ **The pinned footer lists exactly what Save writes**, and Save is off until something changes. A
 * password alone goes to the VPS without committing the account list.
 * ⚠ **The lock is on the PAGE.** The form sends the saved values back unchanged; the server itself
 * would still accept a different one.
 */
import { useEffect, useRef, useState, type ReactNode, type RefObject } from 'react'
import { Lock } from 'lucide-react'
import {
  useRegisterAccount,
  useSetAccountPassword,
  useTerminalSuggestion,
  useTestChannel,
} from '@/hooks/useBots'
import { useBrokerProfiles } from '@/hooks/useLab'
import { brokerName } from '@/lib/brokerName'
import type { BotAccountGroup, BotAccountRegistration, ChannelKind } from '@/types'
import { Change, SectionTitle } from './drawerParts'

/**
 * What an account is called on screen: the nickname somebody gave it, else its broker, else `null`.
 *
 * 🔴 **The nickname LEADS (2026-09-13, Aaron: *"PU Prime Ltd doesn't help me differentiate
 * accounts"*).** The card heading, the account panel and the bot panel put the broker first while
 * the Name field below says it is "used instead of the broker when it is set", and the unassigned
 * list and the go-live panel already put the nickname first — one rule written five times, two
 * copies the other way round. Every place that names an account calls this.
 */
export function accountName(reg: BotAccountRegistration | undefined): string | null {
  return reg?.label || reg?.broker || null
}

/** The account card's and panel's name — `accountName`, or what a group that is not an account is. */
export function nameOf(reg: BotAccountRegistration | undefined, g: BotAccountGroup): string {
  if (g.kind === 'bench') return 'Not on an account'
  if (g.kind === 'unknown') return 'Unreadable configs'
  return accountName(reg) ?? `Account ${g.account}`
}

/**
 * A registered account nobody is trading yet.
 *
 * ⚠ **`cap_agrees: true` with `risk_cap_pct: null` is the honest reading of an empty account** —
 * no bot states a cap, so there is nothing to disagree about and nothing is capped. Writing
 * `cap_agrees: false` here would draw the disagreement banner over an account with no bots on it.
 */
export function emptyGroup(a: BotAccountRegistration): BotAccountGroup {
  return {
    account: a.account,
    server: a.server,
    kind: 'account',
    bots: [],
    risk_cap_pct: null,
    cap_agrees: true,
    cap_unknown: false,
    stacked: false,
    // No bots, so nothing has been handed out and there is nothing that could overflow. `0`
    // rather than `null` on purpose: `null` here means "a share could not be read", and an
    // account with no bots on it has no unreadable share — it has none at all.
    share_total_pct: 0,
    share_overflow_reason: null,
    share_note: null,
    // No cap yet, so nothing to measure room against — `null`, never a number.
    room_pct: null,
    magic_clash: [],
    // A group synthesized here stands in for an account nothing on `/bots/accounts` names (no
    // bots on it now, or none ever) — this app never learned whether it was pinned, and `false`
    // is the safe reading: it just means this account does not jump the queue or open by
    // default until the real group (with the real answer) arrives.
    pinned: false,
  }
}

/** Which card the settings open on — the heading's checklist sends the reader to the fix. */
export type SettingsFocus = 'mt5' | 'password' | 'channels'

/**
 * The symbol ending's THREE states, as three choices. `null` ("not recorded") leaves a moved bot's
 * symbol alone and says so; `""` ("bare names") really strips the ending. 🔴 **The old checkbox
 * said "unticked means bare symbols" while unticked SENT null** — and ticked with an empty box sent
 * `""`, the one value that silently rewrites a live instrument. A choice cannot be misread that way.
 */
type SuffixMode = 'suffix' | 'bare' | 'unknown'
const modeOf = (s: string | null): SuffixMode =>
  s === null ? 'unknown' : s === '' ? 'bare' : 'suffix'
const suffixWords = (s: string | null) =>
  s === null ? 'not recorded' : s === '' ? 'bare names' : s

/** `C:\Program Files\PU Prime MT5 Terminal\terminal64.exe` → `PU Prime MT5 Terminal`. */
const terminalName = (p: string) =>
  p
    .split(/[\\/]/)
    .filter((part) => part && !/\.exe$/i.test(part))
    .pop() ?? p

export function AccountForm({
  existing,
  focus = null,
  onClose,
  frame,
}: {
  /** The account being changed. Absent for the by-hand add, which types every MT5 fact. */
  existing?: BotAccountRegistration
  /** Open on (and re-open to) one card. `at` makes a second request for the same card count. */
  focus?: { to: SettingsFocus; at: number } | null
  onClose: () => void
  /**
   * The panel this form sits in, handed the body and the Save row. The Save row goes in that
   * panel's PINNED footer — inside the scrolling body it was a box within a box, and the first
   * thing to scroll away.
   */
  frame: (body: ReactNode, footer: ReactNode) => ReactNode
}) {
  const save = useRegisterAccount()
  const setPassword = useSetAccountPassword()
  const profiles = useBrokerProfiles()

  const locked = !!existing
  const [account, setAccount] = useState(existing ? String(existing.account) : '')
  const [label, setLabel] = useState(existing?.label ?? '')
  const [broker, setBroker] = useState(existing?.broker ?? '')
  const [tier, setTier] = useState(existing?.tier ?? '')
  const [kind, setKind] = useState(existing ? existing.kind : 'demo')
  const [server, setServer] = useState(existing?.server ?? '')
  // A kind the broker did not state as demo or live is the one locked fact a person must supply.
  const kindUnknown = locked && kind !== 'demo' && kind !== 'live'

  // 🔴 An account with NO terminal asks the box which one it is logged into, and the field starts
  // on that answer (Aaron, 2026-09-13: *"it should be prepopulated"*). Only the reader's EDIT is
  // state, so an answer landing after the form opened still reaches an untouched field and never
  // replaces a typed one. What is offered, and what is refused and why, is the server's
  // (`_suggest_terminal`). ⚠ The person's Save is what records it — Sync still never sets one.
  const asksBox = !!existing && !existing.mt5_path
  const box = useTerminalSuggestion(existing?.account ?? 0, asksBox)
  const suggested = asksBox ? (box.data?.row?.suggested_terminal ?? null) : null
  const [pathEdit, setPathEdit] = useState<string | null>(null)
  const [pathByHand, setPathByHand] = useState(false)
  const mt5Path = pathEdit ?? (existing?.mt5_path || suggested || '')

  // ⚠ A new account starts on NOT RECORDED — the state whose worst case is a move that keeps the
  // symbol and says so. The old default was a ticked box with nothing in it, which sent `""`.
  const [suffixMode, setSuffixMode] = useState<SuffixMode>(
    existing ? modeOf(existing.symbol_suffix) : 'unknown'
  )
  const [suffix, setSuffix] = useState(existing?.symbol_suffix ?? '')
  const [suffixByHand, setSuffixByHand] = useState(false)
  const suffixValue = suffixMode === 'unknown' ? null : suffixMode === 'bare' ? '' : suffix.trim()
  const suffixMissing = suffixMode === 'suffix' && !suffix.trim()

  const [profile, setProfile] = useState(existing?.account_profile ?? '')
  const [password, setPwd] = useState('')
  // Open when there is nothing stored to keep; otherwise one click away. `pwdAsked` autofocuses the
  // box only when somebody asked for it, never on an ordinary open.
  const [pwdAsked, setPwdAsked] = useState(focus?.to === 'password')
  const [pwdOpen, setPwdOpen] = useState(
    !existing || existing.has_password === false || focus?.to === 'password'
  )
  // A NEW request from the heading while the settings are already open. Adjusted during render —
  // React's own pattern for state that follows a prop — so the box is open in the same paint,
  // rather than in an effect that paints once with it still closed.
  const [seenFocus, setSeenFocus] = useState(focus?.at)
  if (focus && focus.at !== seenFocus) {
    setSeenFocus(focus.at)
    if (focus.to === 'password') {
      setPwdAsked(true)
      setPwdOpen(true)
    }
  }
  const [tradeChat, setTradeChat] = useState(existing?.telegram_trade_chat ?? '')
  const [signalChat, setSignalChat] = useState(existing?.telegram_signal_chat ?? '')
  const [healthChat, setHealthChat] = useState(existing?.telegram_health_chat ?? '')

  // ── open on the card the heading's checklist asked for ──────────────────────────────────
  const mt5Ref = useRef<HTMLElement>(null)
  const channelsRef = useRef<HTMLElement>(null)
  const pwdRef = useRef<HTMLInputElement>(null)
  const tradeRef = useRef<HTMLInputElement>(null)
  const signalRef = useRef<HTMLInputElement>(null)
  const healthRef = useRef<HTMLInputElement>(null)
  useEffect(() => {
    if (!focus) return
    if (focus.to === 'password') {
      pwdRef.current?.focus()
      return
    }
    const card = focus.to === 'channels' ? channelsRef.current : mt5Ref.current
    card?.scrollIntoView({ block: 'nearest' })
    if (focus.to === 'channels') {
      // The first EMPTY one, read off the boxes themselves so this runs per request, not per key.
      const first = [tradeRef, signalRef].find((r) => r.current && !r.current.value.trim())
      ;(first ?? tradeRef).current?.focus({ preventScroll: true })
    }
  }, [focus])

  const num = Number(account)
  const live = kind === 'live'
  // What a LIVE account would still owe if saved as it stands — said here, before the save, rather
  // than as the refusal a later move would meet. The server's own list is the authority once saved.
  const owed = [
    ...(live && !tradeChat.trim() ? ['trades'] : []),
    ...(live && !signalChat.trim() ? ['signals'] : []),
  ]

  // ── exactly what Save would write ───────────────────────────────────────────────────────
  const changes: { label: string; from: string; to: string }[] = []
  if (existing) {
    const diff = (what: string, from: string, to: string) => {
      if (from !== to) changes.push({ label: what, from: from || 'none', to: to || 'none' })
    }
    diff('Name', existing.label, label)
    diff('Tier', existing.tier, tier)
    if (existing.account_profile !== profile)
      changes.push({
        label: 'Cost model',
        from: brokerName(existing.account_profile) || 'none',
        to: brokerName(profile) || 'none',
      })
    diff('Demo or live', existing.kind, kind)
    if (existing.mt5_path !== mt5Path)
      changes.push({
        label: 'Terminal',
        from: existing.mt5_path ? terminalName(existing.mt5_path) : 'none',
        to: mt5Path ? terminalName(mt5Path) : 'none',
      })
    if (existing.symbol_suffix !== suffixValue)
      changes.push({
        label: 'Symbols',
        from: suffixWords(existing.symbol_suffix),
        to: suffixWords(suffixValue),
      })
    diff('Trades channel', existing.telegram_trade_chat ?? '', tradeChat.trim())
    diff('Signals channel', existing.telegram_signal_chat ?? '', signalChat.trim())
    diff('Health channel', existing.telegram_health_chat ?? '', healthChat.trim())
  }
  const rowChanged = changes.length > 0
  if (existing && password)
    changes.push({
      label: 'Password',
      from: existing.has_password === true ? 'stored' : 'none',
      to: 'new',
    })

  const valid = Number.isFinite(num) && num > 0 && server.trim().length > 0 && !suffixMissing
  const pending = save.isPending || setPassword.isPending
  const canSave = valid && !pending && (!existing || changes.length > 0)
  const passwordOnly = !!existing && !rowChanged && !!password

  const done = () => {
    setPwd('')
    onClose()
  }
  const submit = () => {
    if (!canSave) return
    if (existing && passwordOnly) {
      // Only the password moved: it goes to the VPS credentials file alone, and the account list
      // is not committed, pushed and pulled for a row that did not change.
      setPassword.mutate({ account: existing.account, password }, { onSuccess: done })
      return
    }
    save.mutate(
      {
        account: num,
        label,
        broker,
        tier,
        kind,
        server,
        mt5_path: mt5Path,
        symbol_suffix: suffixValue,
        account_profile: profile,
        telegram_trade_chat: tradeChat.trim(),
        telegram_signal_chat: signalChat.trim(),
        telegram_health_chat: healthChat.trim(),
        note: existing?.note ?? '',
        // Sent on the SAME request when there is one, so the credential lands before the registry
        // row is committed and pushed — a registered account with no password is a visible, fixable
        // state, while a pushed row whose password write failed afterwards reads as complete.
        password: password || undefined,
        deploy: true,
      },
      { onSuccess: done }
    )
  }

  const channelAccount = Number.isFinite(num) && num > 0 ? num : 0

  const body = (
    <div data-testid="account-form" className="flex flex-col gap-4 pt-4">
      {/* ── MT5 account — the terminal's, not yours ─────────────────────────────── */}
      <Card
        title="MT5 account"
        innerRef={mt5Ref}
        aside={
          locked ? (
            <span
              data-testid="mt5-locked"
              title="The MT5 terminal on the VPS is the source for these, and for the login, server and demo-or-live in the heading. To change one, change it on the terminal and run Sync VPS — an account a bot trades is never changed under it."
              className="inline-flex items-center gap-[5px] text-[11px] text-text-tertiary cursor-help"
            >
              <Lock size={11} /> Locked · Sync VPS updates these
            </span>
          ) : (
            <span
              title="For an account the scan can't see, such as one on a stopped terminal. Sync VPS checks these against the terminal once it can."
              className="text-[11px] text-text-tertiary cursor-help"
            >
              Typed by hand
            </span>
          )
        }
      >
        <dl className={FACTS}>
          {!locked && (
            <>
              <Fact label="Login" hint="The MT5 account number.">
                <input
                  type="number"
                  data-testid="f-account"
                  value={account}
                  onChange={(e) => setAccount(e.target.value)}
                  className={inputCls}
                />
              </Fact>
              <Fact
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
              </Fact>
            </>
          )}

          <Fact
            label="Broker"
            wide={locked}
            hint="The broker's company name, as the terminal reports it."
          >
            {locked ? (
              <span data-testid="f-broker">
                {broker || <span className="text-text-tertiary">Not recorded</span>}
              </span>
            ) : (
              <input
                data-testid="f-broker"
                value={broker}
                placeholder="PU Prime"
                onChange={(e) => setBroker(e.target.value)}
                className={inputCls}
              />
            )}
          </Fact>

          {(!locked || kindUnknown) && (
            <Fact
              label="Type"
              wide={locked}
              hint="A live account is tinted and warned on before every fleet action, and needs its own trades and signals channels."
            >
              <div className="flex items-center gap-2 flex-wrap">
                <select
                  data-testid="f-kind"
                  value={kind}
                  onChange={(e) => setKind(e.target.value)}
                  className={`${inputCls} w-auto`}
                >
                  {kindUnknown && (
                    <option value={kind} disabled>
                      {kind || 'not stated'}
                    </option>
                  )}
                  <option value="demo">Demo</option>
                  <option value="live">Live</option>
                </select>
                {kindUnknown && (
                  <span className="text-[11.5px] text-warn-text">
                    The broker didn&rsquo;t say demo or live — pick the true one.
                  </span>
                )}
              </div>
            </Fact>
          )}

          <Fact
            label="Terminal"
            wide
            hint="The terminal on the VPS logged into this account. Without one no bot can be assigned — a move would be written, pushed, and then fail at connect time."
          >
            {!locked ? (
              // ⚠ The placeholder is NOT a real path. It was the demo bots' terminal, and on
              // 2026-09-13 that exact path was typed onto a new LIVE account — a bot added there
              // would have logged the demo bots' terminal out from under them.
              <input
                data-testid="f-path"
                value={mt5Path}
                placeholder="the terminal64.exe logged into this account"
                onChange={(e) => setPathEdit(e.target.value)}
                className={inputCls}
              />
            ) : existing?.mt5_path ? (
              <span data-testid="f-path" className="font-mono text-[12px] break-all">
                {existing.mt5_path}
              </span>
            ) : (
              <div className="flex flex-col gap-[5px]">
                {pathByHand ? (
                  <input
                    data-testid="f-path"
                    autoFocus
                    value={mt5Path}
                    placeholder="the terminal64.exe logged into this account"
                    onChange={(e) => setPathEdit(e.target.value)}
                    className={inputCls}
                  />
                ) : suggested ? (
                  <span data-testid="f-path" className="font-mono text-[12px] break-all">
                    {suggested}
                  </span>
                ) : null}
                <TerminalNote
                  loading={box.isLoading}
                  failed={box.isError}
                  answer={box.data}
                  filled={!pathByHand && !!suggested}
                />
                {!pathByHand && !suggested && (
                  <button
                    type="button"
                    data-testid="f-path-by-hand"
                    onClick={() => setPathByHand(true)}
                    title="Only for a terminal the VPS cannot ask, such as a stopped one. A path that is not logged into this account fails when a bot connects."
                    className={`${linkCls} self-start`}
                  >
                    Enter the path by hand
                  </button>
                )}
              </div>
            )}
          </Fact>

          <Fact
            label="Symbols"
            wide
            hint="How this broker ends its instrument names. A bot pointed at a symbol its terminal does not quote connects, warms up and receives no bars, which looks exactly like a quiet market."
          >
            {!locked || suffixByHand ? (
              <div className="flex items-center gap-2 flex-wrap">
                <select
                  data-testid="f-suffix-mode"
                  value={suffixMode}
                  onChange={(e) => setSuffixMode(e.target.value as SuffixMode)}
                  className={`${inputCls} w-auto`}
                >
                  <option value="suffix">End in a suffix</option>
                  <option value="bare">Bare names — no suffix</option>
                  <option value="unknown">Not recorded</option>
                </select>
                {suffixMode === 'suffix' && (
                  <input
                    data-testid="f-suffix"
                    value={suffix}
                    placeholder=".p"
                    onChange={(e) => setSuffix(e.target.value)}
                    className={`${inputCls} w-[80px]`}
                  />
                )}
                <span className="text-[11.5px] text-text-tertiary">
                  {suffixMode === 'suffix' ? (
                    <>
                      <span className="font-mono">XAUUSD</span> becomes{' '}
                      <span className="font-mono">XAUUSD{suffix.trim() || '.p'}</span>
                    </>
                  ) : suffixMode === 'bare' ? (
                    <>
                      <span className="font-mono">XAUUSD.s</span> becomes{' '}
                      <span className="font-mono">XAUUSD</span>
                    </>
                  ) : (
                    'A bot moved here keeps the symbol it had.'
                  )}
                </span>
              </div>
            ) : existing?.symbol_suffix === null ? (
              <span className="inline-flex items-center gap-[10px]">
                <span data-testid="f-suffix-shown" className="text-warn-text">
                  Not recorded
                </span>
                <button
                  type="button"
                  data-testid="f-suffix-by-hand"
                  onClick={() => {
                    setSuffixByHand(true)
                    setSuffixMode('suffix')
                  }}
                  className={linkCls}
                >
                  Set by hand
                </button>
              </span>
            ) : existing?.symbol_suffix === '' ? (
              <span data-testid="f-suffix-shown">
                Bare names <span className="text-text-tertiary">— e.g. </span>
                <span className="font-mono">XAUUSD</span>
              </span>
            ) : (
              <span data-testid="f-suffix-shown">
                <span className="font-mono">{existing?.symbol_suffix}</span>
                <span className="text-text-tertiary"> — e.g. </span>
                <span className="font-mono">XAUUSD{existing?.symbol_suffix}</span>
              </span>
            )}
          </Fact>

          {/* THE TRADING PASSWORD (2026-09-11). A read-only "investor" password logs in and reads
           *  prices, then the broker refuses every order (10017 "trade disabled"). So does an
           *  account the broker has switched trading off on — no password fixes that one. */}
          <Fact
            label="Password"
            wide
            hint="Stored on the VPS in a git-ignored file and never shown again."
          >
            {pwdOpen ? (
              <div className="flex flex-col gap-[5px]">
                {existing?.has_password === false && (
                  <span className="text-[11.5px] text-warn-text">
                    None stored — a bot put here cannot log in.
                  </span>
                )}
                <div className="flex items-center gap-[10px]">
                  <input
                    ref={pwdRef}
                    type="password"
                    data-testid="f-password"
                    autoFocus={pwdAsked}
                    value={password}
                    autoComplete="new-password"
                    placeholder={existing ? 'New trading password' : 'The trading password'}
                    onChange={(e) => setPwd(e.target.value)}
                    className={`${inputCls} max-w-[260px]`}
                  />
                  {existing && existing.has_password !== false && (
                    <button
                      type="button"
                      onClick={() => {
                        setPwd('')
                        setPwdOpen(false)
                      }}
                      className={linkCls}
                    >
                      Keep the current one
                    </button>
                  )}
                </div>
                <span className="text-[11.5px] text-text-tertiary leading-[1.4]">
                  The trading password — not a read-only &ldquo;investor&rdquo; one, which logs in
                  and then has every order refused.
                </span>
              </div>
            ) : (
              <span className="inline-flex items-center gap-[10px]">
                <span
                  data-testid="f-password-state"
                  className={
                    existing?.has_password === true ? 'text-text-secondary' : 'text-text-tertiary'
                  }
                >
                  {existing?.has_password === true
                    ? 'Stored on the VPS'
                    : 'Unknown — the VPS could not be asked'}
                </span>
                <button
                  type="button"
                  data-testid="f-password-replace"
                  onClick={() => {
                    setPwdAsked(true)
                    setPwdOpen(true)
                  }}
                  className={linkCls}
                >
                  {existing?.has_password === true ? 'Replace' : 'Set one'}
                </button>
              </span>
            )}
          </Fact>
        </dl>
      </Card>

      {/* ── What only this app knows ───────────────────────────────────────────── */}
      <Card
        title="In this app"
        hint="Yours, not the broker's — how this app names and prices the account."
      >
        <div className="grid grid-cols-[minmax(0,1.2fr)_minmax(0,1.2fr)_minmax(0,0.7fr)] gap-3">
          <Field
            label="Name"
            hint="Shown instead of the broker's name everywhere this account is listed."
          >
            <input
              data-testid="f-label"
              value={label}
              placeholder={broker || 'A name you will recognise'}
              onChange={(e) => setLabel(e.target.value)}
              className={inputCls}
            />
          </Field>
          <Field
            label="Cost model"
            hint="Which measured broker costs price the backtests of this account's bots."
          >
            {/* ⚠ Only the measured profiles are offered, so a name the server would refuse cannot
             *  be typed. A list that could not be READ falls back to a text box rather than
             *  offering nothing — an unread list is not an empty one. */}
            {profiles.isError ? (
              <input
                data-testid="f-profile"
                value={profile}
                placeholder="puprime_ecn"
                onChange={(e) => setProfile(e.target.value)}
                className={inputCls}
              />
            ) : (
              <select
                data-testid="f-profile"
                value={profile}
                onChange={(e) => setProfile(e.target.value)}
                className={inputCls}
              >
                <option value="">Not set</option>
                {[
                  ...(profile && !profiles.data?.some((p) => p.id === profile) ? [profile] : []),
                  ...(profiles.data ?? []).map((p) => p.id),
                ].map((id) => (
                  <option key={id} value={id}>
                    {brokerName(id)}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <Field label="Tier" hint="The broker's own word for the account type. Display only.">
            <input
              value={tier}
              placeholder="ECN"
              onChange={(e) => setTier(e.target.value)}
              className={inputCls}
            />
          </Field>
        </div>
      </Card>

      {/* ── WHERE THIS ACCOUNT REPORTS (2026-09-13) ──────────────────────────────────
       *  🔴 Aaron's rule the day a second person's live account joined the box: each LIVE
       *  account names its own trades and signals channels, neither owner reads the other's
       *  fills, and a bot on a live account with no channel refuses to start. Health is optional
       *  — most of it is about the box every account shares. Every row has a Send test, because
       *  a wrong id fails silently at the moment a real fill is sent. */}
      <Card
        title="Telegram"
        testId="f-channels"
        innerRef={channelsRef}
        hint="Where this account's bots post. Send test posts a real message from the trading box, through the same sender a bot uses; it saves nothing."
        aside={
          owed.length > 0 && (
            <span
              data-testid="f-channels-owed"
              title="A live account needs these before a bot can trade on it — a bot here would refuse to start, and none can be added until they are set."
              className="text-[11.5px] text-warn-text cursor-help"
            >
              Needs its {owed.join(' and ')} channel
            </span>
          )
        }
      >
        <div className="grid grid-cols-[88px_minmax(0,1fr)_auto] gap-x-3 gap-y-[10px] items-center">
          <ChannelRow
            kind="trade"
            name="Trades"
            required={live}
            hint="Where fills are posted. Paste the channel id (a minus and thirteen digits) or its public @name — the Telegram bot must be a member."
            value={tradeChat}
            onChange={setTradeChat}
            account={channelAccount}
            inputRef={tradeRef}
          />
          <ChannelRow
            kind="signal"
            name="Signals"
            required={live}
            hint="Where setups are posted before they fill."
            value={signalChat}
            onChange={setSignalChat}
            account={channelAccount}
            inputRef={signalRef}
          />
          <ChannelRow
            kind="health"
            name="Health"
            required={false}
            hint="Starts, stops, deploys and warnings. Box-wide alerts go to the shared health room either way."
            value={healthChat}
            onChange={setHealthChat}
            account={channelAccount}
            inputRef={healthRef}
          />
        </div>
      </Card>
    </div>
  )

  // ── pinned: exactly what Save writes, and the way out ─────────────────────────────────
  const footer = (
    <div className="flex items-center gap-3">
      <div className="min-w-0 flex-1">
        {existing ? (
          changes.length === 0 ? (
            <p className="text-[12px] text-text-tertiary">No changes</p>
          ) : (
            <div data-testid="form-changes" className="flex flex-wrap gap-[6px]">
              {changes.map((c) => (
                <Change key={c.label} label={c.label} from={c.from} to={c.to} />
              ))}
            </div>
          )
        ) : (
          !valid && (
            <p className="text-[12px] text-text-tertiary">
              {suffixMissing
                ? 'Type the suffix, or pick another choice for the symbols.'
                : 'Needs the login and the server.'}
            </p>
          )
        )}
      </div>
      <button
        onClick={onClose}
        className="shrink-0 px-3 py-[6px] rounded-md text-[12px] border border-border-default text-text-secondary hover:bg-bg-hover hover:text-text-primary transition-colors"
      >
        Cancel
      </button>
      <button
        data-testid="save-account"
        disabled={!canSave}
        onClick={submit}
        title={
          passwordOnly
            ? 'Stores the password on the VPS. Nothing is committed.'
            : 'Committed, pushed and pulled onto the VPS. No secret goes into the repo.'
        }
        className="shrink-0 px-4 py-[6px] rounded-md text-[12.5px] font-semibold bg-accent-muted text-accent-text border border-accent/50 hover:bg-accent/15 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {pending ? 'Saving…' : existing ? 'Save' : 'Add account'}
      </button>
    </div>
  )

  return <>{frame(body, footer)}</>
}

const inputCls =
  'w-full bg-bg-base border border-border-default rounded px-2 py-[5px] ' +
  'text-small text-text-primary'

const linkCls = 'text-[11.5px] text-accent-text hover:underline underline-offset-2'

/** Label | value | label | value. A `wide` row spans the three columns after its label. */
const FACTS =
  'grid grid-cols-[76px_minmax(0,1fr)_76px_minmax(0,1fr)] gap-x-3 gap-y-[12px] items-baseline'

function Card({
  title,
  hint,
  aside,
  testId,
  innerRef,
  children,
}: {
  title: string
  hint?: string
  aside?: ReactNode
  testId?: string
  innerRef?: RefObject<HTMLElement>
  children: ReactNode
}) {
  return (
    <section
      ref={innerRef}
      data-testid={testId}
      className="rounded-lg border border-border-subtle px-4 pt-[10px] pb-4"
    >
      <SectionTitle hint={hint} aside={aside}>
        {title}
      </SectionTitle>
      {children}
    </section>
  )
}

function Fact({
  label,
  hint,
  wide = false,
  children,
}: {
  label: string
  hint?: string
  wide?: boolean
  children: ReactNode
}) {
  return (
    <>
      <dt title={hint} className={`text-[11.5px] text-text-tertiary ${hint ? 'cursor-help' : ''}`}>
        {label}
      </dt>
      <dd className={`min-w-0 text-[12.5px] text-text-primary ${wide ? 'col-span-3' : ''}`}>
        {children}
      </dd>
    </>
  )
}

function Field({ label, hint, children }: { label: string; hint: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-[5px] min-w-0">
      <span title={hint} className="text-[11.5px] text-text-tertiary cursor-help self-start">
        {label}
      </span>
      {children}
    </label>
  )
}

/**
 * What the box said about this account's terminal. Every reason is the SERVER's own sentence
 * (`terminal_note`); this only says whether the box was asked and picks the tone.
 *
 * ⚠ **Three states kept apart**: still asking, could not ask, and asked — and "asked" found
 * nothing is its own sentence, never an empty line that reads like a scan still running.
 */
function TerminalNote({
  loading,
  failed,
  answer,
  filled,
}: {
  loading: boolean
  failed: boolean
  answer: ReturnType<typeof useTerminalSuggestion>['data']
  filled: boolean
}) {
  let text: string
  let tone = 'text-text-tertiary'
  if (loading) {
    text = 'Asking the VPS which terminal is logged into this account…'
  } else if (failed || !answer) {
    text = "Couldn't ask the VPS which terminal is logged into this account."
    tone = 'text-warn-text'
  } else if (!answer.asked) {
    text = `The VPS would not scan its terminals: ${answer.reason ?? 'no reason given'}`
    tone = 'text-warn-text'
  } else {
    const note = answer.row?.terminal_note ?? ''
    if (filled) {
      text = `Filled in from the VPS. ${note} Saved when you save.`
      tone = 'text-text-secondary'
    } else if (note) {
      text = note
      tone = answer.row?.suggested_terminal ? 'text-text-tertiary' : 'text-warn-text'
    } else {
      text = 'No terminal the VPS could ask is logged into this account.'
      tone = 'text-warn-text'
    }
  }
  return (
    <span data-testid="f-path-note" className={`text-[11.5px] leading-[1.4] ${tone}`}>
      {text}
    </span>
  )
}

/**
 * One channel as a row of the Telegram card: its name, the box, its Send test, and the verdict.
 *
 * ⚠ **A verdict belongs to the VALUE it tested.** It is stored with that value and shown only while
 * the field still holds it — so editing the id after a green test cannot leave a green tick beside
 * an id nobody has tested.
 *
 * 🔴 **THREE outcomes, not two.** `ok: null` means the box could not be reached, so NOTHING was
 * tested — rendered neutral, never as a failed channel, or the reader goes hunting for a wrong id
 * that was always right.
 */
function ChannelRow({
  kind,
  name,
  required,
  hint,
  value,
  onChange,
  account,
  inputRef,
}: {
  kind: ChannelKind
  name: string
  /** Owed on a live account; blank elsewhere means the shared room. */
  required: boolean
  hint: string
  value: string
  onChange: (v: string) => void
  account: number
  inputRef: RefObject<HTMLInputElement>
}) {
  const test = useTestChannel()
  const [verdict, setVerdict] = useState<{
    value: string
    ok: boolean | null
    detail: string
  } | null>(null)
  const typed = value.trim()
  const shown = verdict && verdict.value === typed ? verdict : null
  const id = `f-chat-${kind}`

  const send = () => {
    if (!typed || !account) return
    test.mutate(
      { account, kind, chat_id: typed },
      {
        onSuccess: (r) => setVerdict({ value: typed, ok: r.ok, detail: r.detail }),
        onError: (e) =>
          setVerdict({
            value: typed,
            ok: null,
            detail: `Not tested — the trading box could not be reached (${
              (e as Error).message
            }). This says nothing about the channel.`,
          }),
      }
    )
  }

  return (
    <>
      <label htmlFor={id} title={hint} className="flex flex-col cursor-help leading-tight">
        <span className="text-[12.5px] text-text-primary">{name}</span>
        <span
          className={`text-[10.5px] ${required && !typed ? 'text-warn-text' : 'text-text-tertiary'}`}
        >
          {required ? 'Required' : 'Optional'}
        </span>
      </label>
      <input
        id={id}
        ref={inputRef}
        data-testid={id}
        value={value}
        placeholder={
          required ? '-100… or @channel' : `Blank = the shared ${name.toLowerCase()} room`
        }
        onChange={(e) => onChange(e.target.value)}
        className={inputCls}
      />
      <button
        type="button"
        data-testid={`test-chat-${kind}`}
        disabled={!typed || !account || test.isPending}
        title={
          !account
            ? 'Enter the login first.'
            : 'Posts a real message from the trading box, through the same sender a bot uses. Saves nothing.'
        }
        onClick={send}
        className="shrink-0 px-[10px] py-[5px] rounded-md border border-border-default text-[11.5px] text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {test.isPending ? 'Sending…' : 'Send test'}
      </button>
      {shown && (
        <span
          data-testid={`chat-verdict-${kind}`}
          data-ok={shown.ok === null ? 'unknown' : String(shown.ok)}
          className={`col-start-2 col-span-2 text-[11.5px] leading-[1.4] ${
            shown.ok === true
              ? 'text-pos-text'
              : shown.ok === false
                ? 'text-warn-text'
                : 'text-text-tertiary'
          }`}
        >
          {shown.ok === true ? 'Arrived. ' : shown.ok === false ? 'Did not arrive. ' : ''}
          {shown.detail}
        </span>
      )}
    </>
  )
}
