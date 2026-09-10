import { AlertTriangle, Check, Loader2, Minus, X } from 'lucide-react'

/**
 * ONE progress readout for a job made of named steps — a bar per step, in order, with the step
 * the job is on MOVING and nothing else moving. First user: the bot deploy (Aaron, 2026-09-10:
 * *"a static disabled button doesn't catch my focus"* / *"stick to one indicator"*).
 *
 * 🔴 **A step's bar is FULL or EMPTY, never part-full.** The steps come from the code doing them,
 * and none of them reports a fraction. So the active step gets a travelling band — *this is
 * running* — rather than a fill that grows. A fill advanced on a clock would move at a speed
 * unrelated to the work, which this app has already learned is worse than no bar at all.
 *
 * ⚠ **Equal-width segments claim ORDER, not duration.** The seconds under each finished step are
 * what says how long it took.
 *
 * ⚠ **`skipped` is drawn differently from `done`**: a step nobody asked for, or one a failure
 * never reached, must not read as having happened. `warn` is a step that finished without the
 * answer it waits for (the bot restarted but has not reported the new code yet) — neither done
 * nor failed.
 */
export type StepState = 'pending' | 'active' | 'done' | 'failed' | 'skipped' | 'warn'

export interface Step {
  key: string
  label: string
  state: StepState
  /** Measured by whoever ran the step. `null` = not started. */
  seconds?: number | null
}

function StepIcon({ state }: { state: StepState }) {
  switch (state) {
    case 'done':
      return <Check size={11} className="text-pos-text shrink-0" />
    case 'failed':
      return <X size={11} className="text-neg-text shrink-0" />
    case 'warn':
      return <AlertTriangle size={11} className="text-amber-400 shrink-0" />
    case 'active':
      return <Loader2 size={11} className="text-accent shrink-0 animate-spin" />
    case 'skipped':
      return <Minus size={11} className="text-text-tertiary shrink-0" />
    default:
      return <span className="w-[6px] h-[6px] mx-[2.5px] rounded-full bg-bg-active shrink-0" />
  }
}

const TRACK_FILL: Record<StepState, string> = {
  done: 'bg-pos-text/70',
  failed: 'bg-neg-text',
  warn: 'bg-amber-400/80',
  active: '',
  skipped: '',
  pending: '',
}

export function StepProgress({
  steps,
  caption,
  testId,
}: {
  steps: Step[]
  /** One sentence under the bar — what the active step is doing, or how it ended. */
  caption?: React.ReactNode
  testId?: string
}) {
  return (
    <div data-testid={testId}>
      <ol
        className="grid gap-[6px]"
        style={{ gridTemplateColumns: `repeat(${steps.length}, minmax(0, 1fr))` }}
      >
        {steps.map((s) => (
          <li key={s.key} data-step={s.key} data-state={s.state} className="min-w-0">
            <div
              className={`relative h-[6px] rounded-full overflow-hidden ${
                s.state === 'skipped' ? 'bg-bg-surface-2/40' : 'bg-bg-active'
              }`}
            >
              {TRACK_FILL[s.state] && (
                <div className={`absolute inset-0 rounded-full ${TRACK_FILL[s.state]}`} />
              )}
              {s.state === 'active' && (
                <div className="absolute inset-y-0 left-0 w-[40%] rounded-full bg-accent animate-step-sweep" />
              )}
            </div>
            <div
              className={`flex items-center gap-[4px] mt-[6px] text-[11px] leading-tight ${
                s.state === 'active'
                  ? 'text-text-primary font-semibold'
                  : s.state === 'pending' || s.state === 'skipped'
                    ? 'text-text-tertiary'
                    : 'text-text-secondary'
              }`}
            >
              <StepIcon state={s.state} />
              <span className="truncate" title={s.label}>
                {s.label}
              </span>
              {s.seconds != null && s.state !== 'skipped' && (
                <span className="ml-auto font-mono tabular-nums text-[10px] text-text-tertiary">
                  {Math.round(s.seconds)}s
                </span>
              )}
            </div>
          </li>
        ))}
      </ol>
      {caption && (
        <p className="text-[12px] leading-[1.5] text-text-secondary mt-[10px]">{caption}</p>
      )}
    </div>
  )
}
