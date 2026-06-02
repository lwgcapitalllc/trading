import { Activity } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useStressTests } from '@/hooks/useStressTests'
import { EmptyState } from '@/components/EmptyState'
import RobustnessGradeBadge from '@/components/RobustnessGradeBadge'

export function StressTests() {
  const navigate = useNavigate()
  const { data: tests, isLoading } = useStressTests()

  return (
    <div>
      <div className="flex items-end gap-3 mb-[18px]">
        <h1 className="text-h1 font-semibold">Stress Tests</h1>
      </div>

      {isLoading && (
        <div className="p-6 text-text-secondary text-sm">Loading…</div>
      )}

      {!isLoading && !tests?.length && (
        <EmptyState
          icon={<Activity size={22} />}
          title="No stress tests yet"
          description="Open any completed backtest and click 'Stress Test' to run one."
        />
      )}

      {!isLoading && !!tests?.length && (
        <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border-subtle text-left">
                <th className="pb-2 pt-3 px-4 text-text-tertiary font-medium">Grade</th>
                <th className="pb-2 pt-3 pr-4 text-text-tertiary font-medium">Strategy</th>
                <th className="pb-2 pt-3 pr-4 text-text-tertiary font-medium">Instrument</th>
                <th className="pb-2 pt-3 pr-4 text-text-tertiary font-medium">Status</th>
                <th className="pb-2 pt-3 pr-4 text-text-tertiary font-medium text-right">Prob Breach</th>
                <th className="pb-2 pt-3 pr-4 text-text-tertiary font-medium text-right">Prob Pass</th>
                <th className="pb-2 pt-3 pr-4 text-text-tertiary font-medium text-right">Created</th>
              </tr>
            </thead>
            <tbody>
              {tests.map(t => (
                <tr
                  key={t.stress_test_id}
                  className="border-b border-border-subtle/50 hover:bg-bg-hover cursor-pointer"
                  onClick={() => navigate(`/stress-tests/${t.stress_test_id}`)}
                >
                  <td className="py-2 px-4">
                    {t.grade
                      ? <RobustnessGradeBadge grade={t.grade} />
                      : <span className="text-text-tertiary text-xs">—</span>
                    }
                  </td>
                  <td className="py-2 pr-4 text-text-primary">{t.strategy_name ?? t.strategy_id}</td>
                  <td className="py-2 pr-4 font-mono text-accent">{t.instrument}</td>
                  <td className="py-2 pr-4">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${
                      t.status === 'complete'         ? 'bg-pos-muted text-pos-text' :
                      t.status.startsWith('failed')   ? 'bg-neg-muted text-neg-text' :
                                                        'bg-warn-muted text-warn-text'
                    }`}>{t.status}</span>
                  </td>
                  <td className="py-2 pr-4 text-right font-mono text-text-secondary">
                    {t.prob_breach != null ? `${(t.prob_breach * 100).toFixed(1)}%` : '—'}
                  </td>
                  <td className="py-2 pr-4 text-right font-mono text-text-secondary">
                    {t.prob_pass_eval != null ? `${(t.prob_pass_eval * 100).toFixed(1)}%` : '—'}
                  </td>
                  <td className="py-2 pr-4 text-right text-text-tertiary text-xs">
                    {new Date(t.created_at * 1000).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
