import type { RunningJobInfo, RunningJobStatus } from '@/types'

// The three independent lock scopes, mirroring backend lab_db._SCOPE_RUNNER_SQL. NT8 is the
// fallback for NULL/unknown runners, exactly as the backend's COALESCE(runner, 'ninjatrader') does.
export type RunnerScope = 'nt8' | 'mt5' | 'python'

export const RUNNER_LABEL: Record<RunnerScope, string> = {
  nt8: 'NT8',
  mt5: 'MT5',
  python: 'Python',
}

export const RUNNER_FULL_LABEL: Record<RunnerScope, string> = {
  nt8: 'NinjaTrader 8',
  mt5: 'MetaTrader 5',
  python: 'Python (local)',
}

/** Accepts runner values ("ninjatrader", "mt5", "python") or platform values ("NT8", "MT5"). */
export function runnerScope(runner?: string | null): RunnerScope {
  const r = (runner ?? '').toLowerCase()
  if (r === 'mt5') return 'mt5'
  if (r === 'python') return 'python'
  return 'nt8'
}

/** The running job holding this runner's lock, or undefined if that scope is idle. */
export function runningJobFor(
  job: RunningJobStatus | undefined,
  runner?: string | null
): RunningJobInfo | undefined {
  return job?.[runnerScope(runner)]
}

/** Why a job on this runner cannot start right now, or `null` when its platform is free.
 *  Worded as the backend's own refusal (`routers/_locks.py::platform_job`), so a greyed button and
 *  the 409 it prevents say the same thing. Added 2026-09-22: Stress Test stayed pressable while a
 *  Python stack held the slot, and its one possible outcome was an error toast. */
export function platformBusyReason(
  job: RunningJobStatus | undefined,
  runner?: string | null
): string | null {
  if (!runningJobFor(job, runner)?.running) return null
  const label = RUNNER_LABEL[runnerScope(runner)]
  return `${label === 'Python' ? 'A' : 'An'} ${label} job is already running — a stress test's walk-forward and sensitivity need the platform free`
}

/** True when the runner is NinjaTrader — the only platform with futures contracts,
 *  injected ruleset foundational params, and NT8-only lab actions. */
export function isNt8Runner(runner?: string | null): boolean {
  return runnerScope(runner) === 'nt8'
}

/** Which ruleset market a runner's runs are evaluated against. MT5 trades FX pairs and the
 *  Python runner trades spot metals off the same broker feed — both evaluate against the
 *  forex rulesets; only NT8 trades futures contracts. */
export function runnerMarket(runner?: string | null): 'forex' | 'futures' {
  return isNt8Runner(runner) ? 'futures' : 'forex'
}
