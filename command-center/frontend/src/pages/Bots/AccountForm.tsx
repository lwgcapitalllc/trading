/**
 * The broker-account form, and the two small helpers the Bots page reads accounts through.
 *
 * 🔴 **This file was `AccountsTab.tsx`, and that tab had not rendered since the 2026-09-05 rebuild**
 * (one list plus two drawers). Its 1,300 unreachable lines went on 2026-09-11; only what the
 * account panel, the Sync VPS drawer and the page itself import is left. Anything added to a
 * component nothing renders is dead on arrival — rule 9 in the frontend.
 */
import { useState } from 'react'
import { X } from 'lucide-react'
import {
  useRegisterAccount,
  useSetAccountPassword,
  useTerminalSuggestion,
  useTestChannel,
} from '@/hooks/useBots'
import type {
  BotAccountGroup,
  BotAccountRegistration,
  BotAccountRegistrationWrite,
  ChannelKind,
} from '@/types'

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
    cap_takes_turns: false,
    // No bots, so nothing has been handed out and there is nothing that could overflow. `0`
    // rather than `null` on purpose: `null` here means "a share could not be read", and an
    // account with no bots on it has no unreadable share — it has none at all.
    share_total_pct: 0,
    share_overflow_reason: null,
    // No cap yet, so nothing to measure room against — `null`, never a number.
    room_pct: null,
    magic_clash: [],
  }
}

export function AccountForm({
  existing,
  prefill,
  onClose,
}: {
  existing?: BotAccountRegistration
  /**
   * Fields MEASURED off a terminal on the box, for an account nobody has registered yet.
   *
   * ⚠ **It fills only what the box could measure.** Label, tier, cost profile and note stay empty
   * on purpose — a guessed cost profile prices every backtest on that account, and this repo
   * refuses an unmeasured cost rather than borrowing a sibling's number. It also carries no
   * password and cannot: the terminal encrypts it at rest.
   *
   * ⚠ **It is a STARTING POINT, not a commit.** Nothing has been written when this form opens;
   * the account exists once somebody saves it, exactly as if it had been typed.
   */
  prefill?: BotAccountRegistrationWrite
  onClose: () => void
}) {
  const save = useRegisterAccount()
  const setPassword = useSetAccountPassword()

  const seed = existing ?? prefill
  const [account, setAccount] = useState(seed?.account ? String(seed.account) : '')
  const [label, setLabel] = useState(seed?.label ?? '')
  const [broker, setBroker] = useState(seed?.broker ?? '')
  const [tier, setTier] = useState(seed?.tier ?? '')
  const [kind, setKind] = useState(seed?.kind ?? 'demo')
  const [server, setServer] = useState(seed?.server ?? '')
  // 🔴 An account with NO terminal asks the box which one it is logged into, and the field starts
  // on that answer (Aaron, 2026-09-13: *"it should be prepopulated"*). Only the reader's EDIT is
  // state, so an answer landing after the form opened still reaches an untouched field and never
  // replaces a typed one. What is offered, and what is refused and why, is the server's
  // (`_suggest_terminal`). ⚠ The person's Save is what records it — Sync still never sets one.
  const asksBox = !!existing && !existing.mt5_path
  const box = useTerminalSuggestion(existing?.account ?? 0, asksBox)
  const suggested = asksBox ? (box.data?.row?.suggested_terminal ?? null) : null
  const [pathEdit, setPathEdit] = useState<string | null>(null)
  const mt5Path = pathEdit ?? (seed?.mt5_path || suggested || '')
  // `null` is a real, distinct value here — "nobody recorded it" — so the control is a checkbox
  // plus a text field rather than an empty string, which would mean "this broker quotes bare
  // symbols" and silently strip the suffix off a live instrument. A discovered account whose
  // suffix could NOT be measured arrives with the box unticked, which is the same claim.
  const [hasSuffix, setHasSuffix] = useState(seed ? seed.symbol_suffix !== null : true)
  const [suffix, setSuffix] = useState(seed?.symbol_suffix ?? '')
  const [profile, setProfile] = useState(seed?.account_profile ?? '')
  const [password, setPwd] = useState('')
  const [tradeChat, setTradeChat] = useState(seed?.telegram_trade_chat ?? '')
  const [signalChat, setSignalChat] = useState(seed?.telegram_signal_chat ?? '')
  const [healthChat, setHealthChat] = useState(seed?.telegram_health_chat ?? '')

  const num = Number(account)
  // What a LIVE account would still owe if saved as it stands — said here, before the save, rather
  // than as the refusal a later move would meet. The server's own list is the authority once saved.
  const owed = [
    ...(kind === 'live' && !tradeChat.trim() ? ['trades'] : []),
    ...(kind === 'live' && !signalChat.trim() ? ['signals'] : []),
  ]
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
        {/* 🔴 A LABELLED WAY OUT, AT THE TOP (2026-09-06). Cancel has always been at the
         *  BOTTOM of this form — past a dozen fields — so the only exit a reader finds is a
         *  12px `X` glyph they have to guess at. Aaron: *"when I hit add an account, there's no
         *  back button. That sucks. Maybe there's a little x. Okay. So that's the x."*
         *
         *  ⚠ **The bottom Cancel STAYS.** This is a scrolling form and the two exits serve
         *  different moments — one for deciding not to start, one for deciding not to finish —
         *  and neither is a duplicate of the other in a pane you cannot see both ends of. */}
        <button
          onClick={onClose}
          className="ml-auto flex items-center gap-[5px] px-[10px] py-[5px] rounded-md border border-border-default text-[11.5px] text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors"
        >
          <X size={11} />
          Cancel
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
            {/* ⚠ The placeholder is NOT a real path. It was the demo bots' terminal, and on
             *  2026-09-13 that exact path was typed onto a new LIVE account — a bot added there
             *  would have logged the demo bots' terminal out from under them. */}
            <input
              data-testid="f-path"
              value={mt5Path}
              placeholder="the terminal64.exe logged into this account"
              onChange={(e) => setPathEdit(e.target.value)}
              className={inputCls}
            />
            {asksBox && (
              <TerminalNote
                loading={box.isLoading}
                failed={box.isError}
                answer={box.data}
                filled={pathEdit === null && !!suggested}
              />
            )}
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

        {/* ── WHERE THIS ACCOUNT REPORTS (2026-09-13) ──────────────────────────────────
         *  🔴 Aaron's rule the day a second person's live account joined the box: each LIVE
         *  account names its own trades and signals channels, neither owner reads the other's
         *  fills, and a bot on a live account with no channel refuses to start. Health is optional
         *  — most of it is about the box every account shares. Every row has a Send test, because
         *  a wrong id fails silently at the moment a real fill is sent. */}
        <div
          data-testid="f-channels"
          className="flex flex-col gap-2 border-t border-border-subtle pt-3"
        >
          <div className="text-small text-text-primary font-semibold">Telegram channels</div>
          {owed.length > 0 && (
            <div
              data-testid="f-channels-owed"
              className="text-micro text-warn-text bg-warn-muted border border-warn/40 rounded px-2 py-[5px] max-w-[720px]"
            >
              A live account needs its {owed.join(' and ')} channel before a bot can trade on it — a
              bot here would refuse to start, and none can be added until it is set.
            </div>
          )}
          <div className="grid grid-cols-1 gap-3 max-w-[720px]">
            <ChannelRow
              kind="trade"
              label="Trades channel"
              hint={
                kind === 'live'
                  ? 'Where fills are posted. Required on a live account. Paste the channel id (a minus and thirteen digits) or its public @name — the Telegram bot must be a member.'
                  : 'Where fills are posted. Blank uses the shared trades room.'
              }
              value={tradeChat}
              onChange={setTradeChat}
              account={Number.isFinite(num) && num > 0 ? num : 0}
            />
            <ChannelRow
              kind="signal"
              label="Signals channel"
              hint={
                kind === 'live'
                  ? 'Where setups are posted before they fill. Required on a live account, the same as trades.'
                  : 'Where setups are posted. Blank uses the shared signals room.'
              }
              value={signalChat}
              onChange={setSignalChat}
              account={Number.isFinite(num) && num > 0 ? num : 0}
            />
            <ChannelRow
              kind="health"
              label="Health channel"
              hint="Optional. Starts, stops, deploys and warnings. Blank uses the shared health room, which is where box-wide alerts go either way."
              value={healthChat}
              onChange={setHealthChat}
              account={Number.isFinite(num) && num > 0 ? num : 0}
            />
          </div>
          <div className="text-micro text-text-tertiary max-w-[720px]">
            Send test posts a real message from the trading box, through the same sender a bot uses.
            It saves nothing — Save account does that.
          </div>
        </div>

        <div className="flex flex-col gap-1 border-t border-border-subtle pt-3">
          {/* THE TRADING PASSWORD (2026-09-11). A read-only "investor" password logs in and reads
           *  prices, then the broker refuses every order (10017 "trade disabled"). So does an
           *  account the broker has switched trading off on — what the live account hit that day,
           *  with the right password stored — and no password fixes that one. */}
          <Field
            label="MT5 password"
            hint="The password your broker gave you for trading. If they also issued a read-only 'investor' password, not that one: with it the bot connects and reads prices, then every order is refused. Stored on the VPS in a git-ignored file and never shown again. Leave blank to keep the current one."
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

/**
 * What the box said about this account's terminal, under the field. Every reason is the SERVER's
 * own sentence (`terminal_note`); this only says whether the box was asked and picks the tone.
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
    text = "Couldn't ask the VPS which terminal is logged into this account. Type the path."
    tone = 'text-warn-text'
  } else if (!answer.asked) {
    text = `The VPS would not scan its terminals: ${answer.reason ?? 'no reason given'}`
    tone = 'text-warn-text'
  } else {
    const note = answer.row?.terminal_note ?? ''
    if (filled) {
      text = `Filled in from the VPS. ${note} Change it if that's wrong.`
      tone = 'text-text-secondary'
    } else if (note) {
      text = note
      tone = answer.row?.suggested_terminal ? 'text-text-tertiary' : 'text-warn-text'
    } else {
      text = 'No terminal the VPS could ask is logged into this account.'
    }
  }
  return (
    <span data-testid="f-path-note" className={`text-micro leading-[1.35] ${tone}`}>
      {text}
    </span>
  )
}

/**
 * One channel field and its Send test.
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
  label,
  hint,
  value,
  onChange,
  account,
}: {
  kind: ChannelKind
  label: string
  hint: string
  value: string
  onChange: (v: string) => void
  account: number
}) {
  const test = useTestChannel()
  const [verdict, setVerdict] = useState<{
    value: string
    ok: boolean | null
    detail: string
  } | null>(null)
  const typed = value.trim()
  const shown = verdict && verdict.value === typed ? verdict : null

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
    <Field label={label} hint={hint}>
      <div className="flex items-center gap-2">
        <input
          data-testid={`f-chat-${kind}`}
          value={value}
          placeholder="-100… or @channel"
          onChange={(e) => onChange(e.target.value)}
          className={inputCls}
        />
        <button
          type="button"
          data-testid={`test-chat-${kind}`}
          disabled={!typed || !account || test.isPending}
          title={!account ? 'Enter the account number first.' : undefined}
          onClick={(e) => {
            // Inside a <label>: stop the click reaching the input the label is for.
            e.preventDefault()
            send()
          }}
          className="shrink-0 px-[10px] py-[5px] rounded-md border border-border-default text-[11.5px] text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {test.isPending ? 'Sending…' : 'Send test'}
        </button>
      </div>
      {shown && (
        <span
          data-testid={`chat-verdict-${kind}`}
          data-ok={shown.ok === null ? 'unknown' : String(shown.ok)}
          className={`text-micro leading-[1.35] ${
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
    </Field>
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
