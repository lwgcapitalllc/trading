/**
 * What an account needs before a bot can trade on it — ALWAYS the same four steps, in the same
 * order, each one marked done, missing, unknown or shared (2026-09-13).
 *
 * 🔴 Aaron: *"in the heading I can't tell what is missing and what is not missing."* The heading
 * drew a chip for SOME states only — `password set` as a grey pill beside `no trades or signals
 * channel · add` as an amber one, the same shape — so a thing that was there and a thing that was
 * not looked alike, and a step with nothing wrong drew nothing at all. A fixed list makes absence
 * visible: every step is on screen every time, and only its state changes.
 *
 * ⚠ **Nothing is decided here.** Every state is read off the server's own fields — `assignable`,
 * `has_password`, `missing_channels` — and `has_password: null` is UNKNOWN, never missing (the VPS
 * could not be asked). ⚠ **A blank channel on an account that owes none is `shared`**: it posts to
 * the shared room. Only the server's `missing_channels` may call a channel missing.
 */
import { AlertTriangle, Check, HelpCircle, Minus } from 'lucide-react'
import type { BotAccountRegistration } from '@/types'
import type { SettingsFocus } from './AccountForm'

export type ReadyState = 'ok' | 'missing' | 'unknown' | 'shared'

export interface ReadyStep {
  key: 'terminal' | 'password' | 'trades' | 'signals'
  name: string
  state: ReadyState
  /** The server's own sentence where it sent one — shown on hover. */
  title: string
  /** Which card of the settings a missing step opens on. */
  fix: SettingsFocus
}

function readinessOf(reg: BotAccountRegistration): ReadyStep[] {
  // ⚠ Null-safe: an answer recorded before 2026-09-13 carries no channel fields at all.
  const owed = reg.missing_channels ?? []
  const channel = (key: 'trades' | 'signals', name: string, chat: string | undefined): ReadyStep =>
    owed.includes(key)
      ? {
          key,
          name,
          state: 'missing',
          title: reg.channels_reason || `No ${key} channel — a bot here would refuse to start.`,
          fix: 'channels',
        }
      : chat
        ? { key, name, state: 'ok', title: `Posts to ${chat}`, fix: 'channels' }
        : {
            key,
            name,
            state: 'shared',
            title: `None named, so this account's bots post to the shared ${key} room.`,
            fix: 'channels',
          }
  return [
    reg.assignable
      ? { key: 'terminal', name: 'Terminal', state: 'ok', title: reg.mt5_path, fix: 'mt5' }
      : {
          key: 'terminal',
          name: 'Terminal',
          state: 'missing',
          title: reg.unassignable_reason || 'No terminal on the VPS is recorded for this account.',
          fix: 'mt5',
        },
    reg.has_password === true
      ? {
          key: 'password',
          name: 'Password',
          state: 'ok',
          title:
            'A password is stored on the trading box. It must be the trading password — with a read-only "investor" one a bot logs in and every order is refused.',
          fix: 'password',
        }
      : reg.has_password === false
        ? {
            key: 'password',
            name: 'Password',
            state: 'missing',
            title: 'No password is stored, so a bot put here cannot log in.',
            fix: 'password',
          }
        : {
            key: 'password',
            name: 'Password',
            state: 'unknown',
            title:
              'The trading box could not be asked whether a password is stored — unknown, not missing.',
            fix: 'password',
          },
    channel('trades', 'Trades channel', reg.telegram_trade_chat),
    channel('signals', 'Signals channel', reg.telegram_signal_chat),
  ]
}

const WORD: Record<ReadyState, string> = {
  ok: '',
  missing: 'missing',
  unknown: 'unknown',
  shared: 'shared room',
}

function StateIcon({ state }: { state: ReadyState }) {
  if (state === 'ok') return <Check size={12} className="text-text-tertiary" />
  if (state === 'missing') return <AlertTriangle size={12} />
  if (state === 'unknown') return <HelpCircle size={12} />
  return <Minus size={12} />
}

/**
 * The four steps as one row under the account's heading. ⚠ **A missing step is a BUTTON** that opens
 * the settings on its own fix; the rest are text. ⚠ **Colour marks only what needs you**: amber for
 * missing, grey for everything else — a stored password is a normal state, never green.
 */
export function ReadinessStrip({
  reg,
  onFix,
}: {
  reg: BotAccountRegistration
  onFix: (to: SettingsFocus) => void
}) {
  return (
    <div data-testid="readiness" className="flex items-center gap-x-[14px] gap-y-[4px] flex-wrap">
      {readinessOf(reg).map((s) => {
        const body = (
          <>
            <StateIcon state={s.state} />
            <span>{s.name}</span>
            {WORD[s.state] && <span className="opacity-80">· {WORD[s.state]}</span>}
          </>
        )
        return s.state === 'missing' ? (
          <button
            key={s.key}
            data-testid={`ready-${s.key}`}
            data-state={s.state}
            title={`${s.title} Click to fix it.`}
            onClick={() => onFix(s.fix)}
            className="inline-flex items-center gap-[5px] text-[11.5px] font-medium text-warn-text hover:underline underline-offset-2"
          >
            {body}
          </button>
        ) : (
          <span
            key={s.key}
            data-testid={`ready-${s.key}`}
            data-state={s.state}
            title={s.title}
            className={`inline-flex items-center gap-[5px] text-[11.5px] cursor-default ${
              s.state === 'ok' ? 'text-text-secondary' : 'text-text-tertiary'
            }`}
          >
            {body}
          </span>
        )
      })}
    </div>
  )
}
