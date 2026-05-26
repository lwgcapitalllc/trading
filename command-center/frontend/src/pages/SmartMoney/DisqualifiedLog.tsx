import { useState } from 'react'
import type { DisqualifiedCandidate } from '@/types'

const REASON_FILTERS = ['All reasons', 'Drawdown', 'Concentration', 'Win rate', 'Activity']

function matchesFilter(reason: string, filter: string): boolean {
  if (filter === 'All reasons') return true
  const r = reason.toLowerCase()
  if (filter === 'Drawdown') return r.includes('drawdown')
  if (filter === 'Concentration') return r.includes('concentrat') || r.includes('single trade') || r.includes('pnl')
  if (filter === 'Win rate') return r.includes('win rate') || r.includes('below') || r.includes('threshold')
  if (filter === 'Activity') return r.includes('week') || r.includes('active') || r.includes('trade count')
  return true
}

export function DisqualifiedLog({ disqualified }: { disqualified: DisqualifiedCandidate[] }) {
  const [reasonFilter, setReasonFilter] = useState('All reasons')
  const [search, setSearch] = useState('')

  const filtered = disqualified
    .filter(d => matchesFilter(d.reason, reasonFilter))
    .filter(d => !search || d.id.toLowerCase().includes(search.toLowerCase()))

  return (
    <div>
      <div className="flex gap-2 mb-3 items-center flex-wrap">
        <div className="flex bg-bg-surface border border-border-subtle rounded-md overflow-hidden">
          {REASON_FILTERS.map(f => (
            <span
              key={f}
              onClick={() => setReasonFilter(f)}
              className={`text-micro px-3 py-[6px] cursor-pointer select-none transition-colors duration-[100ms] ${reasonFilter === f ? 'bg-accent-muted text-text-primary' : 'text-text-secondary hover:bg-bg-hover'}`}
            >
              {f}
            </span>
          ))}
        </div>
        <div className="relative">
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Filter disqualified IDs"
            className="bg-bg-surface border border-border-subtle rounded-md pl-[30px] pr-[11px] py-[6px] text-small text-text-primary w-[210px] focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent-muted placeholder:text-text-tertiary"
          />
          <svg className="absolute left-[10px] top-1/2 -translate-y-1/2 w-[13px] h-[13px] text-text-tertiary" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>
          </svg>
        </div>
        <span className="ml-auto text-micro text-text-tertiary">{filtered.length} of {disqualified.length}</span>
      </div>

      <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              {['Wallet / account', 'Market', 'Source', 'Stage removed', 'Disqualification reason'].map(h => (
                <th key={h} className="text-left text-[10px] font-semibold uppercase tracking-[0.7px] text-text-tertiary px-[14px] py-[10px] bg-bg-surface-2 border-b border-border-subtle whitespace-nowrap">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((d, i) => (
              <tr key={i} className="border-b border-border-subtle last:border-0">
                <td className="px-[14px] py-[11px] font-mono text-[11px]">
                  {d.id.length > 20 ? `${d.id.slice(0, 10)}…${d.id.slice(-6)}` : d.id}
                </td>
                <td className="px-[14px] py-[11px]">
                  <span className={`inline-flex text-[10px] font-semibold px-2 py-[3px] rounded-pill uppercase tracking-[0.4px] ${d.market === 'crypto' ? 'bg-accent-muted text-accent-text' : 'bg-gold-muted text-gold-text'}`}>
                    {d.market}
                  </span>
                </td>
                <td className="px-[14px] py-[11px] text-text-secondary text-small">{d.source}</td>
                <td className="px-[14px] py-[11px] font-mono text-[11px] text-text-secondary">{d.stage}</td>
                <td className="px-[14px] py-[11px]">
                  <span className="inline-flex text-[10px] font-normal px-[9px] py-[3px] rounded-pill bg-neg-muted text-neg-text">
                    {d.reason}
                  </span>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={5} className="text-center py-12 text-text-tertiary text-small">
                  No disqualified candidates match the current filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-3 text-micro text-text-tertiary bg-bg-sunken border border-border-subtle rounded-md px-3 py-[10px] flex gap-2 items-start">
        <svg className="w-[14px] h-[14px] flex-shrink-0 mt-[1px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>
        <span>Nothing is silently dropped — every removed candidate is logged with its reason and the stage that removed it, per the pipeline spec.</span>
      </div>
    </div>
  )
}
