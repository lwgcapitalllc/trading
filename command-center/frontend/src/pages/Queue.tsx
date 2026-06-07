import { ListOrdered, Trash2 } from 'lucide-react'
import { useQueue, useDeleteQueueItem } from '@/hooks/useQueue'
import { EmptyState } from '@/components/EmptyState'
import type { QueueItem } from '@/types'

function StatusPill({ status }: { status: QueueItem['status'] }) {
  const cfg = {
    pending:  { label: 'Pending',  cls: 'bg-bg-surface text-text-secondary border-border-default' },
    running:  { label: 'Running',  cls: 'bg-accent/10 text-accent border-accent/30' },
    done:     { label: 'Done',     cls: 'bg-pos-muted text-pos-text border-pos-text/30' },
    failed:   { label: 'Failed',   cls: 'bg-neg-muted text-neg-text border-neg-text/30' },
  }[status] ?? { label: status, cls: 'bg-bg-surface text-text-secondary border-border-default' }

  return (
    <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${cfg.cls}`}>
      {cfg.label}
    </span>
  )
}

function fmtTs(unix: number | null) {
  if (!unix) return '—'
  return new Date(unix * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function jobLabel(item: QueueItem) {
  if (item.job_type === 'optimization') {
    return `Optimization · ${(item.payload.optimization_id as string).slice(0, 8)}`
  }
  if (item.job_type === 'stress_test') {
    const extras = [
      item.payload.include_walk_forward && 'WF',
      item.payload.include_sensitivity && 'Sens',
    ].filter(Boolean).join('+')
    return `Stress Test · ${(item.payload.stress_test_id as string).slice(0, 8)}${extras ? ` (${extras})` : ''}`
  }
  return item.job_type
}

export function Queue() {
  const { data: items, isLoading } = useQueue()
  const del = useDeleteQueueItem()

  return (
    <div>
      <div className="flex items-end gap-3 mb-[18px]">
        <h1 className="text-h1 font-semibold">Queue</h1>
        {items && items.length > 0 && (
          <span className="mb-[3px] text-sm text-text-secondary font-mono tabular-nums">
            {items.filter(i => i.status === 'pending').length} pending
            {items.filter(i => i.status === 'running').length > 0 && ', 1 running'}
          </span>
        )}
      </div>

      {isLoading && (
        <div className="p-6 text-text-secondary text-sm">Loading…</div>
      )}

      {!isLoading && !items?.length && (
        <EmptyState
          icon={<ListOrdered size={22} />}
          title="Queue is empty"
          description="Add optimizations or stress tests to the queue via their detail pages."
        />
      )}

      {!isLoading && !!items?.length && (
        <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border-subtle text-left">
                <th className="pb-2 pt-3 px-4 text-text-tertiary font-medium w-10">#</th>
                <th className="pb-2 pt-3 pr-4 text-text-tertiary font-medium">Job</th>
                <th className="pb-2 pt-3 pr-4 text-text-tertiary font-medium">Status</th>
                <th className="pb-2 pt-3 pr-4 text-text-tertiary font-medium">Queued</th>
                <th className="pb-2 pt-3 pr-4 text-text-tertiary font-medium">Started</th>
                <th className="pb-2 pt-3 pr-4 text-text-tertiary font-medium">Finished</th>
                <th className="pb-2 pt-3 pr-4 text-text-tertiary font-medium w-10" />
              </tr>
            </thead>
            <tbody>
              {items.map(item => (
                <tr key={item.queue_id} className="border-b border-border-subtle/50">
                  <td className="py-2 px-4 font-mono tabular-nums text-text-tertiary">
                    {item.position}
                  </td>
                  <td className="py-2 pr-4">
                    <div className="font-mono text-xs text-text-primary">{jobLabel(item)}</div>
                    {item.error && (
                      <div className="text-neg-text text-[11px] mt-0.5 truncate max-w-xs">{item.error}</div>
                    )}
                  </td>
                  <td className="py-2 pr-4"><StatusPill status={item.status} /></td>
                  <td className="py-2 pr-4 font-mono tabular-nums text-text-secondary text-xs">
                    {fmtTs(item.created_at)}
                  </td>
                  <td className="py-2 pr-4 font-mono tabular-nums text-text-secondary text-xs">
                    {fmtTs(item.started_at)}
                  </td>
                  <td className="py-2 pr-4 font-mono tabular-nums text-text-secondary text-xs">
                    {fmtTs(item.finished_at)}
                  </td>
                  <td className="py-2 pr-4">
                    {item.status === 'pending' && (
                      <button
                        onClick={() => del.mutate(item.queue_id)}
                        disabled={del.isPending && del.variables === item.queue_id}
                        className="text-text-tertiary hover:text-neg-text transition-colors disabled:opacity-40"
                        title="Remove from queue"
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
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
