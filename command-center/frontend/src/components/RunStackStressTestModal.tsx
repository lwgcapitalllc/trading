/**
 * Stress test a whole SHARED ACCOUNT — Monte Carlo, walk-forward and sensitivity over the combined
 * book, graded as one result.
 *
 * Its single-run twin is `RunStressTestModal` in `pages/BacktestDetail.tsx`, and the flow is
 * deliberately the same one: pick what to grade against, choose how many walk-forward windows, and
 * read what the arithmetic already says about them before spending an hour.
 *
 * 🔴 **A SCREEN CANNOT BE GRADED AND THE BUTTON IS NOT OFFERED ON ONE.** There every leg traded its
 * own full account with nothing able to block anything, so the combined figure is N standalone runs
 * added up — an upper bound. Putting a letter on it would be a grade for a result no account can
 * produce, which is worse than refusing because it looks like an answer. The server refuses it in
 * those words; this never gets there.
 *
 * ⚠ **The sample floor is measured on the COMBINED book, and that is the point.** Aaron's stated
 * design is that sample size arrives at the PORTFOLIO level, so two legs that each trade too rarely
 * to grade alone can clear the floor together. That is one account's trade history, honestly — not
 * a way of buying trades by loosening anything.
 */

import { useMemo, useState } from 'react'
import { toast } from 'sonner'
import { useRunStressTest } from '@/hooks/useStressTests'
import { useRulesets } from '@/hooks/useLab'

/** Mirrors the backend's own floor (`routers/stress_tests.MIN_TRADES_FOR_STRESS`). Below it the
 *  WHOLE test is refused, not just a phase — the grade leans on Monte Carlo tail percentiles small
 *  samples cannot estimate. */
const MIN_TRADES_FOR_STRESS = 100
/** Mirrors the backend's per-window floor. Below it a window is excluded as not-assessable, which
 *  caps the grade at B — arithmetic, knowable before a single replay runs. */
const WF_MIN_TRADES_PER_WINDOW = 20

interface Props {
  stackId: string
  /** The COMBINED book's trade count, or `null` when it could not be read.
   *
   *  ⚠ Three-state on purpose: `null` is "nobody could tell me", never zero. It is what a stack
   *  whose shared report has not arrived looks like, and rendering it as 0 would say the account
   *  never traded — which then reads as a refusal the reader cannot act on. */
  trades: number | null
  onClose: () => void
  navigate: (path: string) => void
}

export function RunStackStressTestModal({ stackId, trades, onClose, navigate }: Props) {
  const runTest = useRunStressTest()
  const { data: rulesets } = useRulesets()

  // A stack has no stored evaluations to pick from — a single run carries the rulesets it was
  // scored against and this does not — so the choice is over the FOREX rulesets, which is what a
  // python stack can be graded by. Every leg here is a python strategy by construction.
  const options = useMemo(() => (rulesets ?? []).filter((r) => r.market === 'forex'), [rulesets])

  // THREE states, and the third is why this is not a plain string. `undefined` means the reader has
  // not chosen, so the first ruleset stands in once they load; `null` means they chose to grade
  // against NOTHING, which is a real answer (Monte Carlo only, no letter). Collapsing the two would
  // make an explicit "no ruleset" silently revert to the default the moment the list arrives.
  //
  // ⚠ DERIVED rather than filled by an effect, so nothing can overwrite a choice already made.
  const [chosen, setChosen] = useState<string | null | undefined>(undefined)
  const rulesetId = chosen === undefined ? options[0]?.id : (chosen ?? undefined)

  const [windows, setWindows] = useState(5)
  const known = trades != null
  const belowFloor = known && trades < MIN_TRADES_FOR_STRESS
  const oosPerWindow = known && windows > 0 ? (trades / windows) * 0.3 : 0
  const wfThin = known && oosPerWindow < WF_MIN_TRADES_PER_WINDOW
  const maxUsableWindows = known ? Math.floor((trades * 0.3) / WF_MIN_TRADES_PER_WINDOW) : 0

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={onClose}
    >
      <div
        data-testid="stack-stress-modal"
        className="bg-bg-surface border border-border-default rounded-xl p-6 w-full max-w-md space-y-4 max-h-[88vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-base font-semibold text-text-primary">Stress test this account</h2>

        <p className="text-xs text-text-secondary leading-relaxed">
          Grades the COMBINED book — every leg on one balance under one risk budget — as a single
          result. Each phase replays the whole set together, never one strategy at a time.
        </p>

        {/* The request still asks for sensitivity; the SERVER decides whether it runs, because the
            evidence (each bot's risk share, the cap, and whether the stack's own run ever hit it)
            lives there. A second copy of that rule here is how the page and the run come to
            describe different tests. */}
        <p data-testid="stack-nudge-rule" className="text-xs text-text-secondary leading-relaxed">
          Setting nudges run only when these bots can compete for risk — their shares add up past
          the cap, one trades off another&rsquo;s results, or the stack&rsquo;s own run lost a trade
          to the cap or cut one by more than 1%. Otherwise each bot&rsquo;s own stress test already
          covers its settings, and the server skips them and says why.
        </p>

        {options.length ? (
          <div className="space-y-1.5">
            <p className="text-xs text-text-secondary">
              Grade against
              <span className="text-text-tertiary">
                {' '}
                — every grade is a statement about drawdown vs this ruleset&rsquo;s limit
              </span>
            </p>
            <select
              value={rulesetId ?? ''}
              onChange={(e) => setChosen(e.target.value || null)}
              className="w-full bg-bg-sunken border border-border-subtle rounded px-2 py-1.5 text-xs text-text-primary"
            >
              <option value="">No ruleset — Monte Carlo only, no letter grade</option>
              {options.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
          </div>
        ) : (
          <p className="text-xs text-text-tertiary">
            No forex ruleset to grade against — Monte Carlo only, and no letter grade.
          </p>
        )}

        <div className="space-y-1.5">
          <label className="text-xs text-text-secondary flex items-center justify-between">
            <span>Walk-forward windows</span>
            <span className="font-mono text-text-tertiary">
              {known ? `≈${oosPerWindow.toFixed(0)} unseen trades each` : 'trade count unknown'}
            </span>
          </label>
          <input
            type="range"
            min={2}
            max={10}
            step={1}
            value={windows}
            onChange={(e) => setWindows(Number(e.target.value))}
            className="w-full accent-accent"
          />
          <div className="flex justify-between text-[10px] text-text-tertiary font-mono">
            <span>2</span>
            <span className="text-text-primary">{windows} windows</span>
            <span>10</span>
          </div>
          {wfThin && (
            <p className="text-[11px] text-warn-text leading-snug">
              Under {WF_MIN_TRADES_PER_WINDOW} unseen trades a window is excluded as not-assessable,
              so the walk-forward will return no number and the grade will be capped at B.
              {maxUsableWindows >= 2
                ? ` Use ${maxUsableWindows} window${maxUsableWindows === 1 ? '' : 's'} or fewer.`
                : ` ${trades} combined trades is not enough for any window to be assessable — run it for the Monte Carlo and sensitivity.`}
            </p>
          )}
        </div>

        {/* The floor is stated where the decision is made, not delivered as a 422 after the click.
            An unknown count is NOT rendered as a refusal — the server holds the real gate and will
            name the figure it measured. */}
        {belowFloor && (
          <p className="text-[11px] text-neg-text leading-snug">
            This account has {trades} combined trades and a stress test needs at least{' '}
            {MIN_TRADES_FOR_STRESS}. Get more trades from more data — a longer period, another
            instrument, another leg — before grading it.
          </p>
        )}

        <p className="text-xs text-text-secondary">
          The exact time estimate comes back from the server when it starts, since it depends on how
          many settings this set actually has. The platform must be idle.
        </p>

        <div className="flex gap-2 pt-2">
          <button
            onClick={() => {
              runTest.mutate(
                {
                  stack_id: stackId,
                  ruleset_id: rulesetId,
                  include_walk_forward: true,
                  include_sensitivity: true,
                  num_simulations: 10_000,
                  num_bootstrap: 1_000,
                  walk_forward_windows: windows,
                },
                {
                  onSuccess: (data) => {
                    // The server's OWN estimate, never a number invented here.
                    if (data.estimated_duration_min) {
                      toast.info(
                        `Estimated ~${data.estimated_duration_min} min · ${data.notes.join(' · ')}`,
                        { duration: 10_000 }
                      )
                    }
                    onClose()
                    navigate(`/stress-tests/${data.stress_test_id}`)
                  },
                }
              )
            }}
            disabled={runTest.isPending || belowFloor}
            className="flex-1 py-1.5 text-sm bg-accent text-bg-base rounded font-medium hover:opacity-90 disabled:opacity-50"
          >
            {runTest.isPending ? 'Starting…' : 'Run Stress Test'}
          </button>
          <button
            onClick={onClose}
            className="px-4 py-1.5 text-sm text-text-secondary border border-border-subtle rounded hover:bg-bg-hover"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}
