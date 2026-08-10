/**
 * Whether a bot's process is alive. Shared by the Monitor tab and the Accounts tab.
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
export function BotStatusPill({ status }: { status: string }) {
  const isRunning = status === 'RUNNING'
  const isError   = status === 'ERROR'
  const cls   = isRunning ? 'bg-pos-muted text-pos-text' : 'bg-neg-muted text-neg-text'
  const label = isRunning ? 'Running' : isError ? 'Error' : 'Stopped'
  return (
    <span className={`inline-flex text-[10px] font-semibold px-2 py-[3px] rounded-pill uppercase tracking-[0.4px] ${cls}`}>
      {label}
    </span>
  )
}
