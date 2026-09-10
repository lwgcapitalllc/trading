import { useState } from 'react'
import { Drawer } from '@/components/Drawer'
import { Shimmer } from '@/components/Shimmer'
import { useTerminalScan } from '@/hooks/useBots'
import type { BotAccountRegistrationWrite, RegistryCheck, ScannedTerminal } from '@/types'
import { AccountForm } from './AccountsTab'

/**
 * What the VPS is ACTUALLY logged into, next to what the account list CLAIMS — in a drawer.
 *
 * 🔴 **The two are shown side by side and never merged.** The box is authoritative about what is
 * logged in; the list stays authoritative about intent. Adopting the box's answer automatically
 * would turn an accidental login into configuration — and the bot-side mismatch halt exists
 * precisely because a terminal's login can change under a running bot. Adding a discovered
 * account is one deliberate click into the same form a typed account goes through.
 *
 * ⚠ **The layout answers a question before it shows data (2026-09-10, Aaron: "I don't know what
 * I'm looking at").** The first version listed three things in a row — new accounts, every
 * terminal, every row of the list — at equal weight, so the reader had to work out the finding
 * themselves. Now: one sentence that IS the finding, then only what needs a decision, then the
 * reference table, then a quiet footnote for what could not be checked.
 *
 * 🔴 **Three failure shapes, rendered as three different things.** The query threw (the box could
 * not be asked — the network), `asked: false` (the box refused — the script), and a terminal that
 * could not be asked (nothing is wrong). Collapsing any pair turns "cannot ask" into "nothing there".
 */
export function VpsScanDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const scan = useTerminalScan()
  // Adding happens INSIDE the drawer, so the reader never loses the list they were deciding from.
  // 'manual' is the by-hand form — the only way in for an account the scan cannot see.
  const [adding, setAdding] = useState<BotAccountRegistrationWrite | 'manual' | null>(null)
  const close = () => {
    setAdding(null)
    onClose()
  }
  const manual = adding === 'manual'

  return (
    <Drawer
      open={open}
      onClose={close}
      label="What is logged in on the VPS"
      title={
        manual
          ? 'Add an account by hand'
          : adding
            ? `Add account #${adding.account}`
            : 'What’s logged in on the VPS'
      }
      subtitle={
        manual ? (
          'For an account the scan can’t see — nothing is written until you save'
        ) : adding ? (
          'Filled in from the VPS — name it and pick its cost profile'
        ) : (
          <Checked scan={scan} />
        )
      }
      actions={
        adding ? (
          <SmallButton onClick={() => setAdding(null)}>Back</SmallButton>
        ) : (
          <SmallButton onClick={() => scan.refetch()} disabled={scan.isFetching}>
            {scan.isFetching && !scan.isPending ? 'Scanning…' : 'Scan again'}
          </SmallButton>
        )
      }
    >
      {adding ? (
        <div className="pt-4">
          {/* Saving invalidates the scan's query, so the account moves out of "not in your list"
              by itself — the drawer confirms the add rather than asking you to trust it. */}
          <AccountForm
            key={manual ? 'manual' : adding.account}
            prefill={manual ? undefined : adding}
            onClose={() => setAdding(null)}
          />
        </div>
      ) : (
        <>
          <ScanContent scan={scan} onAdd={setAdding} />
          <ManualAdd onClick={() => setAdding('manual')} />
        </>
      )}
    </Drawer>
  )
}

/**
 * The by-hand way in, deliberately quiet and deliberately ALWAYS there.
 *
 * ⚠ **Rendered under every state — first scan still running, scan failed, box refused.** A
 * stopped terminal can never appear in the scan, and a scan can take minutes; hiding this until
 * the scan answers would leave that account with no way onto the list at all.
 * ⚠ **Quiet on purpose.** Typing an account in is how the list went wrong before; the found
 * accounts above are the path to take, this is the fallback.
 */
function ManualAdd({ onClick }: { onClick: () => void }) {
  return (
    <div className="mt-6 pt-4 border-t border-border-subtle text-small text-text-tertiary">
      Not listed?{' '}
      <button
        data-testid="add-account"
        onClick={onClick}
        className="text-text-secondary underline underline-offset-2 hover:text-text-primary"
      >
        Add it by hand
      </button>{' '}
      — for a terminal that isn’t running, which the scan can’t read.
    </div>
  )
}

type Scan = ReturnType<typeof useTerminalScan>

function Checked({ scan }: { scan: Scan }) {
  // FIRST read only — `isPending` is "no answer yet", and a failed read is not pending, so a dead
  // link can never sit behind a placeholder looking busy.
  if (scan.isPending) return <Shimmer className="h-[12px] w-[170px]" />
  if (!scan.data?.scanned_at) return <>Couldn’t scan</>
  const n = scan.data.terminals.length
  return (
    <>
      Scanned {new Date(scan.data.scanned_at).toLocaleTimeString()}
      {scan.data.asked ? ` · ${n} terminal${n === 1 ? '' : 's'}` : ''}
    </>
  )
}

function ScanContent({
  scan,
  onAdd,
}: {
  scan: Scan
  onAdd: (suggested: BotAccountRegistrationWrite) => void
}) {
  if (scan.isPending) return <ScanSkeleton />
  const failed = scan.isError ? String((scan.error as Error)?.message ?? scan.error) : null
  // The query THREW and there is nothing earlier to show: the question was not answered. About
  // the channel, never about accounts.
  if (!scan.data) {
    return (
      <div className="pt-4">
        <Banner tone="neg" title="The VPS couldn’t be asked">
          {failed}
          <p className="mt-2 opacity-80">
            Nothing here is a statement about your accounts — the question wasn’t answered.
          </p>
        </Banner>
      </div>
    )
  }
  // The box ANSWERED and refused. A different repair from the one above: the script, not the network.
  if (!scan.data.asked) {
    return (
      <div className="pt-4">
        <Banner tone="warn" title="The VPS refused the scan">
          {scan.data.reason}
        </Banner>
      </div>
    )
  }

  const found = scan.data.terminals.filter((t) => t.verdict === 'new' && t.suggested)
  const wrong = scan.data.registry.filter((r) => r.verdict === 'contradicted')
  const matches = scan.data.registry.filter((r) => r.verdict === 'confirmed')
  const unchecked = scan.data.registry.filter((r) => r.verdict === 'unverified')

  return (
    <div className="flex flex-col gap-6 pt-4">
      {/* A RE-scan that failed keeps the last good answer on screen, and says it is the last one:
          blanking it would throw away a real reading because a later question went unanswered. */}
      {failed && (
        <Banner tone="neg" title="The latest scan failed — showing the previous one">
          {failed}
        </Banner>
      )}
      <Summary found={found.length} wrong={wrong.length} />

      {found.length > 0 && (
        <Section title="Not in your list yet">
          {found.map((t) => (
            <FoundAccount key={t.key} terminal={t} onAdd={onAdd} />
          ))}
        </Section>
      )}

      {wrong.length > 0 && (
        <Section title="Your list doesn’t match the VPS">
          {wrong.map((r) => (
            <WrongRow key={r.account} check={r} />
          ))}
        </Section>
      )}

      <Section title="Terminals on the VPS">
        <div className="rounded-md border border-border-subtle divide-y divide-border-subtle">
          {scan.data.terminals.map((t) => (
            <TerminalRow key={t.key} terminal={t} />
          ))}
        </div>
      </Section>

      {/* ⚠ Deliberately QUIET. "Could not be checked" is not a finding against a row, and giving it
          the weight of one is what teaches somebody to scroll past the real finding above. */}
      {(matches.length > 0 || unchecked.length > 0) && (
        <div className="text-small text-text-tertiary">
          <p>
            Your list:{' '}
            {[
              matches.length > 0 &&
                `${matches.length} match${matches.length === 1 ? 'es' : ''} the VPS`,
              wrong.length > 0 && `${wrong.length} doesn’t`,
              unchecked.length > 0 && `${unchecked.length} couldn’t be checked`,
            ]
              .filter(Boolean)
              .join(' · ')}
          </p>
          {unchecked.length > 0 && (
            <details className="mt-2">
              <summary className="cursor-pointer hover:text-text-secondary">
                Why some couldn’t be checked
              </summary>
              <ul className="mt-2 flex flex-col gap-1 pl-3">
                {unchecked.map((r) => (
                  <li key={r.account}>
                    #{r.account}
                    {r.label ? ` · ${r.label}` : ''} — {r.detail}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </div>
  )
}

/**
 * The first scan's placeholder, shaped like what lands: the one-line answer, then the terminal
 * list. Section titles are fixed words, so they render REAL rather than shimmering.
 */
function ScanSkeleton() {
  return (
    <div className="flex flex-col gap-6 pt-4">
      <Shimmer shape="block" className="h-[56px] w-full" />
      <Section title="Terminals on the VPS">
        <div className="rounded-md border border-border-subtle divide-y divide-border-subtle">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="px-3 py-[9px] flex items-center justify-between">
              <Shimmer className="h-[13px] w-[110px]" />
              <Shimmer className="h-[13px] w-[120px]" />
            </div>
          ))}
        </div>
      </Section>
    </div>
  )
}

/** The finding, in one sentence, before any data. */
function Summary({ found, wrong }: { found: number; wrong: number }) {
  if (found === 0 && wrong === 0) {
    return (
      <Banner tone="pos" title="Everything logged in on the VPS is in your list">
        Nothing to add, and nothing in your list contradicts what the VPS reports.
      </Banner>
    )
  }
  const parts = [
    found > 0 &&
      `${found} account${found === 1 ? ' is' : 's are'} logged in on the VPS but not in your list`,
    wrong > 0 && `your list is wrong about ${wrong} account${wrong === 1 ? '' : 's'}`,
  ].filter(Boolean) as string[]
  const sentence = parts.join(', and ')
  return (
    <Banner tone="warn" title={sentence.charAt(0).toUpperCase() + sentence.slice(1) + '.'}>
      {found > 0 ? 'Add it below — nothing is written until you save.' : 'Details below.'}
    </Banner>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <p className="text-[9px] font-semibold uppercase tracking-[0.8px] text-gold-text">{title}</p>
      {children}
    </section>
  )
}

function Banner({
  tone,
  title,
  children,
}: {
  tone: 'neg' | 'warn' | 'pos'
  title: string
  children?: React.ReactNode
}) {
  const tint = {
    neg: 'bg-neg-muted border-neg/50 text-neg-text',
    warn: 'bg-warn-muted border-warn/50 text-warn-text',
    pos: 'bg-pos-muted border-pos/50 text-pos-text',
  }[tone]
  return (
    <div className={`rounded-md border px-3 py-[10px] text-small ${tint}`}>
      <p className="font-semibold">{title}</p>
      {children && <div className="mt-1 opacity-90">{children}</div>}
    </div>
  )
}

function SmallButton({
  onClick,
  disabled,
  children,
}: {
  onClick: () => void
  disabled?: boolean
  children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="text-[12px] px-[10px] py-[5px] rounded-md border border-border-default text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors disabled:opacity-50"
    >
      {children}
    </button>
  )
}

/**
 * An account the VPS is logged into that the list has never heard of.
 *
 * ⚠ **A LIVE account is called out in words, not only in colour.** It is the row that can cost
 * real money, and it is exactly the case this whole feature was built after.
 */
function FoundAccount({
  terminal,
  onAdd,
}: {
  terminal: ScannedTerminal
  onAdd: (suggested: BotAccountRegistrationWrite) => void
}) {
  const live = terminal.kind === 'live'
  return (
    <div
      className={`rounded-md border px-3 py-3 ${
        live ? 'bg-neg-muted border-neg/50' : 'bg-bg-sunken border-border-subtle'
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-body font-semibold text-text-primary">#{terminal.account}</span>
            <KindPill terminal={terminal} />
            <span className="text-small text-text-tertiary">on {shortName(terminal.install)}</span>
          </div>
          <p className="text-small text-text-secondary mt-1">
            {[
              terminal.server,
              terminal.company,
              terminal.currency,
              terminal.leverage ? `1:${terminal.leverage}` : null,
            ]
              .filter(Boolean)
              .join(' · ')}
          </p>
        </div>
        <button
          onClick={() => terminal.suggested && onAdd(terminal.suggested)}
          className="text-[12px] px-3 py-[6px] rounded-md bg-accent text-text-inverse hover:bg-accent-hover shrink-0"
        >
          Add to list
        </button>
      </div>
      {live && (
        <p className="text-small text-neg-text mt-2">
          Real money. Adding it only puts it in your list — no bot moves onto it until you say so,
          and a bot can’t connect until its password is stored.
        </p>
      )}
    </div>
  )
}

function WrongRow({ check }: { check: RegistryCheck }) {
  return (
    <div className="rounded-md border border-neg/50 bg-neg-muted px-3 py-[10px]">
      <p className="text-small font-semibold text-text-primary">
        #{check.account}
        {check.label ? ` · ${check.label}` : ''}
      </p>
      {check.conflicts.length > 0 ? (
        <ul className="text-small text-neg-text mt-1 flex flex-col gap-1">
          {check.conflicts.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      ) : (
        <p className="text-small text-neg-text mt-1">{check.detail}</p>
      )}
    </div>
  )
}

/**
 * One terminal, one line: which install, which account, and — only when it needs saying — why.
 *
 * 🔴 **`account: null` never renders alone.** The status line says why it is empty, because a
 * terminal nobody asked and a terminal with no account look identical otherwise.
 */
function TerminalRow({ terminal }: { terminal: ScannedTerminal }) {
  // ⚠ **No bot COUNT.** "Owned by" comes from which bot configs name this terminal, and a benched
  // bot still names it — the first wording said "3 bots trade here" with one of the three
  // trading nothing. A number that includes a bot that is not trading is a wrong number.
  const status =
    terminal.state === 'owned_by_bot'
      ? terminal.account !== null
        ? 'Your bots’ terminal — account reported by the bot'
        : 'Your bots’ terminal — no bot has reported its account yet'
      : terminal.state === 'not_running'
        ? 'Not running, so it couldn’t be checked'
        : terminal.account === null
          ? (terminal.error ?? 'Couldn’t read an account')
          : null
  return (
    <div className="px-3 py-[9px]">
      <div className="flex items-center justify-between gap-3">
        <span className="text-small text-text-primary truncate" title={terminal.install}>
          {shortName(terminal.install)}
        </span>
        <span className="text-small shrink-0 flex items-center gap-2">
          {terminal.account !== null ? (
            <>
              <span className="text-text-primary font-mono">#{terminal.account}</span>
              <KindPill terminal={terminal} />
            </>
          ) : (
            <span className="text-text-tertiary">—</span>
          )}
        </span>
      </div>
      {status && <p className="text-[11.5px] text-text-tertiary mt-[2px]">{status}</p>}
    </div>
  )
}

/**
 * Demo or live, and what to say when it is not known.
 *
 * ⚠ **"Not reported" and "unrecognised" are different, and the first version rendered both as a
 * yellow "mode unknown".** A bot reports only the account NUMBER, so a bot-sourced row has no mode
 * by design — nothing is wrong, and a warning colour there is a false alarm on the one terminal
 * that matters most. A terminal the scan itself asked that answered with a flag it did not
 * recognise IS an anomaly, and keeps the warning: guessing "demo" for real money is the failure.
 */
function KindPill({ terminal }: { terminal: ScannedTerminal }) {
  if (terminal.kind === null) {
    if (terminal.account_source === 'bot') {
      return (
        <span
          className="text-small text-text-tertiary"
          title="The bot reports which account it is on, not whether it is demo or live."
        >
          demo/live not reported
        </span>
      )
    }
    return (
      <span
        className="text-small text-warn-text"
        title="The terminal answered with an account type this app does not recognise — whether it is real money is unknown."
      >
        type unknown
      </span>
    )
  }
  return (
    <span
      className={`text-small ${terminal.kind === 'live' ? 'text-neg-text' : 'text-text-tertiary'}`}
    >
      {terminal.kind}
    </span>
  )
}

/** `C:\MT5_Scalper` → `MT5_Scalper`. The full path stays in the row's tooltip. */
function shortName(install: string): string {
  const parts = install.split(/[\\/]/).filter(Boolean)
  return parts[parts.length - 1] ?? install
}
