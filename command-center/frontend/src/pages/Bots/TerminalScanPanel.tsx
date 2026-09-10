import { useTerminalScan } from '@/hooks/useBots'
import type { RegistryCheck, ScannedTerminal } from '@/types'

/**
 * What the VPS is ACTUALLY logged into, next to what the account list CLAIMS.
 *
 * 🔴 **The two are shown side by side and never merged.** The box is authoritative about what is
 * logged in; the list stays authoritative about intent. Adopting the box's answer automatically
 * would turn an accidental login into configuration — and the bot-side mismatch halt exists
 * precisely because a terminal's login can change under a running bot, so auto-adopting would be
 * resolving that alarm by agreeing with it. Adding a discovered account is one deliberate click
 * into the same form a typed account goes through.
 *
 * 🔴 **Three failure shapes, rendered as three different things.** A scan that could not RUN (the
 * query threw), a scan the box REFUSED (`asked: false`), and a terminal that could not be ASKED
 * (state `not_running` / `owned_by_bot`) are separate facts with separate repairs — the network,
 * the script, and nothing-is-wrong respectively. Collapsing any pair of them is how "cannot ask"
 * becomes "nothing there".
 *
 * ⚠ **`unverified` is deliberately quiet.** It is not a finding against a row, and tinting it like
 * one would flag every account on the bots' own terminal on every single scan — which is what
 * teaches somebody to scroll past the real one.
 */
export function TerminalScanPanel({
  onAdd,
}: {
  onAdd: (suggested: NonNullable<ScannedTerminal['suggested']>) => void
}) {
  const scan = useTerminalScan()

  const found = (scan.data?.terminals ?? []).filter((t) => t.verdict === 'new' && t.suggested)
  const conflicts = (scan.data?.terminals ?? []).filter((t) => t.verdict === 'conflict')

  return (
    <div className="bg-bg-surface border border-border-subtle rounded-lg h-full flex flex-col">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border-subtle shrink-0">
        <div className="min-w-0">
          <p className="text-[9px] font-semibold uppercase tracking-[0.8px] text-gold-text">
            What the VPS is logged into
          </p>
          <p className="text-small text-text-tertiary mt-[2px] truncate">
            {scan.isFetching
              ? 'Asking the box…'
              : scan.data?.scanned_at
                ? `Checked ${new Date(scan.data.scanned_at).toLocaleTimeString()}`
                : 'Not checked yet'}
          </p>
        </div>
        <button
          onClick={() => scan.refetch()}
          disabled={scan.isFetching}
          className="text-small px-3 py-[6px] rounded-md border border-border-default
                     text-text-secondary hover:bg-bg-hover disabled:opacity-50 shrink-0"
        >
          {scan.isFetching ? 'Checking…' : 'Check again'}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">
        {/* The scan could not RUN. This is about the CHANNEL — unreachable box, unreadable
            output — and it must never render as a box with nothing on it. */}
        {scan.isError && (
          <Block tone="neg" title="The box could not be asked">
            {String((scan.error as Error)?.message ?? scan.error)}
            <p className="text-text-tertiary mt-2">
              Nothing below is a statement about your accounts — the question was not answered.
            </p>
          </Block>
        )}

        {/* The box ANSWERED and refused. A different repair from the one above, so a different
            block: this sends you at the script, not at the network. */}
        {scan.data && !scan.data.asked && (
          <Block tone="warn" title="The box refused the scan">
            {scan.data.reason}
          </Block>
        )}

        {scan.data?.asked && (
          <>
            {found.length > 0 && (
              <section className="flex flex-col gap-2">
                <SectionTitle>Logged in on the box, not in your list ({found.length})</SectionTitle>
                {found.map((t) => (
                  <FoundAccount key={t.key} terminal={t} onAdd={onAdd} />
                ))}
              </section>
            )}

            {conflicts.length > 0 && (
              <section className="flex flex-col gap-2">
                <SectionTitle>The box disagrees with your list ({conflicts.length})</SectionTitle>
                {conflicts.map((t) => (
                  <Block key={t.key} tone="neg" title={`Account ${t.account} — ${t.install}`}>
                    <ul className="flex flex-col gap-1">
                      {t.conflicts.map((c) => (
                        <li key={c}>{c}</li>
                      ))}
                    </ul>
                  </Block>
                ))}
              </section>
            )}

            <section className="flex flex-col gap-2">
              <SectionTitle>Terminals ({scan.data.terminals.length})</SectionTitle>
              {scan.data.terminals.map((t) => (
                <TerminalRow key={t.key} terminal={t} />
              ))}
            </section>

            {scan.data.registry.length > 0 && (
              <section className="flex flex-col gap-2">
                <SectionTitle>Your account list, checked</SectionTitle>
                {scan.data.registry.map((r) => (
                  <CheckRow key={r.account} check={r} />
                ))}
              </section>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[9px] font-semibold uppercase tracking-[0.8px] text-text-tertiary">
      {children}
    </p>
  )
}

function Block({
  tone,
  title,
  children,
}: {
  tone: 'neg' | 'warn' | 'pos' | 'neutral'
  title: string
  children: React.ReactNode
}) {
  const tint = {
    neg: 'bg-neg-muted border-neg text-neg-text',
    warn: 'bg-warn-muted border-warn text-warn-text',
    pos: 'bg-pos-muted border-pos text-pos-text',
    neutral: 'bg-bg-sunken border-border-subtle text-text-secondary',
  }[tone]
  return (
    <div className={`rounded-md border px-3 py-2 text-small ${tint}`}>
      <p className="font-semibold mb-1">{title}</p>
      {children}
    </div>
  )
}

/**
 * An account the box is logged into that the list has never heard of.
 *
 * ⚠ **A LIVE account is called out rather than tinted like a success.** It is the row that can
 * cost real money, and it arrives here because somebody logged a terminal in — which is exactly
 * the case this whole feature was built after.
 */
function FoundAccount({
  terminal,
  onAdd,
}: {
  terminal: ScannedTerminal
  onAdd: (suggested: NonNullable<ScannedTerminal['suggested']>) => void
}) {
  const live = terminal.kind === 'live'
  return (
    <div
      className={`rounded-md border px-3 py-3 flex items-start justify-between gap-3 ${
        live ? 'bg-neg-muted border-neg' : 'bg-bg-sunken border-border-subtle'
      }`}
    >
      <div className="min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-body font-semibold text-text-primary">#{terminal.account}</span>
          <KindPill kind={terminal.kind} />
        </div>
        <p className="text-small text-text-secondary mt-1">
          {terminal.server}
          {terminal.company ? ` · ${terminal.company}` : ''}
          {terminal.currency ? ` · ${terminal.currency}` : ''}
          {terminal.leverage ? ` · 1:${terminal.leverage}` : ''}
        </p>
        <p className="text-small text-text-tertiary mt-1 font-mono truncate">{terminal.install}</p>
        {/* The suffix is a MEASUREMENT and how it was made travels with it — an unmeasured one
            says so rather than showing a blank, which would read as "bare symbols". */}
        <p className="text-small text-text-tertiary mt-1">
          {terminal.symbol_suffix === null
            ? `Symbol suffix not measured — ${terminal.symbol_suffix_how ?? 'no reason given'}`
            : `Instruments end "${terminal.symbol_suffix}" — ${terminal.symbol_suffix_how}`}
        </p>
        {live && (
          <p className="text-small text-neg-text mt-2">
            This is a REAL-MONEY account. Adding it only puts it in the list; no bot moves onto it
            until you say so, and it needs a password stored before one could connect.
          </p>
        )}
      </div>
      <button
        onClick={() => terminal.suggested && onAdd(terminal.suggested)}
        className="text-small px-3 py-[6px] rounded-md bg-accent text-text-inverse
                   hover:bg-accent-hover shrink-0"
      >
        Add to list
      </button>
    </div>
  )
}

function TerminalRow({ terminal }: { terminal: ScannedTerminal }) {
  return (
    <div className="rounded-md border border-border-subtle bg-bg-sunken px-3 py-2">
      <div className="flex items-center justify-between gap-3">
        <span className="text-small font-mono text-text-secondary truncate">
          {terminal.install}
        </span>
        {terminal.account !== null ? (
          <span className="text-small text-text-primary shrink-0">
            #{terminal.account} <KindPill kind={terminal.kind} />
            {/* A bot's report and the scan's own reading are different strengths of evidence,
                so where the number came from is on screen rather than implied. */}
            {terminal.account_source === 'bot' && (
              <span className="text-text-tertiary"> · reported by the bot</span>
            )}
          </span>
        ) : (
          <span className="text-small text-text-tertiary shrink-0">not asked</span>
        )}
      </div>
      {/* `account: null` NEVER stands alone. The reason is the whole difference between a
          terminal with no account and a question nobody put. */}
      {terminal.account === null && (terminal.reason || terminal.error) && (
        <p className="text-small text-text-tertiary mt-1">{terminal.reason ?? terminal.error}</p>
      )}
    </div>
  )
}

function CheckRow({ check }: { check: RegistryCheck }) {
  const tone =
    check.verdict === 'contradicted'
      ? 'text-neg-text'
      : check.verdict === 'confirmed'
        ? 'text-pos-text'
        : 'text-text-tertiary'
  return (
    <div className="rounded-md border border-border-subtle bg-bg-sunken px-3 py-2">
      <div className="flex items-center justify-between gap-3">
        <span className="text-small text-text-secondary truncate">
          #{check.account}
          {check.label ? ` · ${check.label}` : ''}
        </span>
        <span className={`text-small shrink-0 ${tone}`}>{check.verdict}</span>
      </div>
      <p className="text-small text-text-tertiary mt-1">{check.detail}</p>
      {check.conflicts.length > 0 && (
        <ul className="text-small text-neg-text mt-1 flex flex-col gap-1">
          {check.conflicts.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

/**
 * ⚠ **Three states, and `null` gets its own word.** An unrecognised account mode is UNKNOWN, not
 * demo — guessing the safe-sounding word for an account that is real is how a bot ends up pointed
 * at somebody's money.
 */
function KindPill({ kind }: { kind: string | null }) {
  if (kind === null) {
    return <span className="text-small text-warn-text">mode unknown</span>
  }
  const tone = kind === 'live' ? 'text-neg-text' : 'text-text-tertiary'
  return <span className={`text-small ${tone}`}>{kind}</span>
}
