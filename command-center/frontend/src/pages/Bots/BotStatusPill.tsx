/**
 * Whether a bot's process is alive, and what it is in the middle of. Shared by the Monitor tab,
 * the Accounts tab and the bot drawer.
 *
 * ⚠ **In its own file rather than exported from `index.tsx`, to avoid a CYCLE.** `index.tsx`
 * imports `AccountsTab`, so `AccountsTab` importing back from `index.tsx` closes a loop — which
 * TypeScript accepts and the bundler resolves, right up until one of the two grows a top-level
 * initialiser and the other reads it as `undefined` at module-evaluation time. That failure looks
 * like a blank tab with a null-reference in the console and points at neither file.
 *
 * ⚠ **It is shared rather than copied because two tabs list the SAME bots.** A second
 * hand-written rendering is how a green "Running" ends up beside a grey "Stopped" for one bot on
 * two tabs, and this is also the pill every other chip on the Monitor row is sized against.
 *
 * ⚠ **There is a `components/StatusPill.tsx` and it is a different thing** — that one renders a
 * lab RUN's status (complete / running / failed). Same word, different domain; merging them would
 * mean one component whose colours have to mean two sets of states.
 */
import { Loader2 } from 'lucide-react'

export type BotAction = 'start' | 'stop' | 'restart'

const ACTION_WORD: Record<BotAction, string> = {
  start: 'Starting',
  stop: 'Stopping',
  restart: 'Restarting',
}

const ACTION_TITLE: Record<BotAction, string> = {
  start: 'Starting this bot on the trading box.',
  stop: 'Asking this bot to stop. It finishes what it is doing and shuts down cleanly — this can take up to half a minute.',
  restart: 'Stopping this bot, then starting it again.',
}

/**
 * A start, stop or restart that is still happening — and it says WHICH.
 *
 * 🔴 **It replaced a pulsing "…" (2026-09-10).** Aaron: *"I am stopping it and I should be seeing
 * the pill saying stopping, not three dots."* Three dots answer *something is happening*; the
 * reader already knows that — they pressed the button. What they need is *which thing*, because
 * stop and restart end in different states and a stop can take half a minute.
 *
 * ⚠ **Shared by the row and the bot drawer**, so the two cannot describe one action differently.
 *
 * ⚠ **On the row it takes the place of the start/stop buttons AND the Logs button.** MEASURED at
 * 1280px: the actions column is 190px, and with Logs and Configure still showing, 62px is left —
 * this pill is 72–84px. Hiding Logs for the length of the action is what lets it fit.
 */
export function BotActionPill({ action }: { action: BotAction }) {
  return (
    <span
      data-testid="bot-action-pill"
      data-action={action}
      title={ACTION_TITLE[action]}
      className="inline-flex items-center gap-[4px] text-[11px] font-medium px-[7px] py-[3px] rounded-pill border border-accent/50 bg-accent/10 text-accent whitespace-nowrap cursor-default"
    >
      <Loader2 size={10} className="animate-spin" />
      {ACTION_WORD[action]}
    </span>
  )
}

export function BotStatusPill({ status }: { status: string }) {
  const isRunning = status === 'RUNNING'
  const isError = status === 'ERROR'
  const cls = isRunning ? 'bg-pos-muted text-pos-text' : 'bg-neg-muted text-neg-text'
  const label = isRunning ? 'Running' : isError ? 'Error' : 'Stopped'
  return (
    <span
      className={`inline-flex text-[10px] font-semibold px-2 py-[3px] rounded-pill uppercase tracking-[0.4px] ${cls}`}
    >
      {label}
    </span>
  )
}
