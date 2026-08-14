import { useState } from 'react'
import { Star } from 'lucide-react'
import type { Candidate } from '@/types'

type Market = 'all' | 'crypto' | 'forex'

interface RankingsProps {
  candidates: Candidate[]
  onSelect: (c: Candidate) => void
  initialMarket?: Market
}

const CONSISTENCY_PILL: Record<string, string> = {
  improving: 'bg-pos-muted text-pos-text',
  stable: 'bg-bg-surface-2 text-text-secondary',
  declining: 'bg-warn-muted text-warn-text',
}

export function Rankings({ candidates, onSelect, initialMarket = 'all' }: RankingsProps) {
  const [market, setMarket] = useState<Market>(initialMarket)
  const [source, setSource] = useState<string>('all')
  const [search, setSearch] = useState('')
  const [sortCol, setSortCol] = useState<keyof Candidate>('rank')
  const [sortAsc, setSortAsc] = useState(true)

  const sources = ['all', ...Array.from(new Set(candidates.map((c) => c.source)))]

  const filtered = candidates
    .filter((c) => market === 'all' || c.market === market)
    .filter((c) => source === 'all' || c.source === source)
    .filter((c) => !search || c.id.toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => {
      const av = a[sortCol] as number
      const bv = b[sortCol] as number
      return sortAsc ? (av > bv ? 1 : -1) : av < bv ? 1 : -1
    })

  const handleSort = (col: keyof Candidate) => {
    if (sortCol === col) setSortAsc((a) => !a)
    else {
      setSortCol(col)
      setSortAsc(false)
    }
  }

  const SortTh = ({
    col,
    label,
    right,
  }: {
    col: keyof Candidate
    label: string
    right?: boolean
  }) => (
    <th
      onClick={() => handleSort(col)}
      className={`text-left text-[10px] font-semibold uppercase tracking-[0.7px] text-text-tertiary px-[14px] py-[10px] bg-bg-surface-2 border-b border-border-subtle whitespace-nowrap cursor-pointer select-none hover:text-text-secondary ${right ? 'text-right' : ''}`}
    >
      {label}
      {sortCol === col ? (sortAsc ? ' ↑' : ' ↓') : ''}
    </th>
  )

  return (
    <div>
      {/* Filter bar */}
      <div className="flex gap-2 mb-3 items-center flex-wrap">
        <div className="flex bg-bg-surface border border-border-subtle rounded-md overflow-hidden">
          {(['all', 'crypto', 'forex'] as Market[]).map((m) => (
            <span
              key={m}
              onClick={() => setMarket(m)}
              className={`text-micro px-3 py-[6px] cursor-pointer select-none capitalize transition-colors duration-[100ms] ${market === m ? 'bg-accent-muted text-text-primary' : 'text-text-secondary hover:bg-bg-hover'}`}
            >
              {m === 'all' ? 'All' : m.charAt(0).toUpperCase() + m.slice(1)}
            </span>
          ))}
        </div>
        <div className="flex bg-bg-surface border border-border-subtle rounded-md overflow-hidden">
          {sources.slice(0, 4).map((s) => (
            <span
              key={s}
              onClick={() => setSource(s)}
              className={`text-micro px-3 py-[6px] cursor-pointer select-none capitalize transition-colors duration-[100ms] ${source === s ? 'bg-accent-muted text-text-primary' : 'text-text-secondary hover:bg-bg-hover'}`}
            >
              {s === 'all' ? 'All sources' : s}
            </span>
          ))}
        </div>
        <div className="relative">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter by wallet / account ID"
            className="bg-bg-surface border border-border-subtle rounded-md pl-[30px] pr-[11px] py-[6px] text-small text-text-primary w-[210px] focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent-muted placeholder:text-text-tertiary"
          />
          <svg
            className="absolute left-[10px] top-1/2 -translate-y-1/2 w-[13px] h-[13px] text-text-tertiary"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <circle cx="11" cy="11" r="7" />
            <path d="m21 21-4.3-4.3" />
          </svg>
        </div>
        <span className="ml-auto text-micro text-text-tertiary tabular-nums">
          {filtered.length === candidates.length
            ? `${filtered.length} candidates`
            : `${filtered.length} of ${candidates.length}`}
        </span>
      </div>

      <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <SortTh col="rank" label="#" />
              <th className="text-left text-[10px] font-semibold uppercase tracking-[0.7px] text-text-tertiary px-[14px] py-[10px] bg-bg-surface-2 border-b border-border-subtle">
                Wallet / account
              </th>
              <th className="text-left text-[10px] font-semibold uppercase tracking-[0.7px] text-text-tertiary px-[14px] py-[10px] bg-bg-surface-2 border-b border-border-subtle">
                Market
              </th>
              <th className="text-left text-[10px] font-semibold uppercase tracking-[0.7px] text-text-tertiary px-[14px] py-[10px] bg-bg-surface-2 border-b border-border-subtle">
                Source
              </th>
              <SortTh col="composite_score" label="Composite" />
              <SortTh col="cum_pnl_usd" label="Cum. PnL" right />
              <SortTh col="peak_drawdown" label="Max DD" right />
              <SortTh col="overall_win_rate" label="Win rate" right />
              <th className="text-left text-[10px] font-semibold uppercase tracking-[0.7px] text-text-tertiary px-[14px] py-[10px] bg-bg-surface-2 border-b border-border-subtle">
                Consistency
              </th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((c) => (
              <tr
                key={c.id}
                onClick={() => onSelect(c)}
                className="cursor-pointer hover:bg-bg-hover transition-colors duration-[100ms] border-b border-border-subtle last:border-0"
              >
                <td
                  className={`px-[14px] py-[11px] font-semibold w-[34px] ${c.rank <= 5 ? 'text-gold-text' : 'text-text-secondary'}`}
                >
                  {c.rank <= 5 ? (
                    <Star size={12} className="inline mr-1 fill-gold-text text-gold-text" />
                  ) : null}
                  {c.rank}
                </td>
                <td className="px-[14px] py-[11px]">
                  <span className="font-mono text-[11px]">
                    {c.id.length > 16 ? `${c.id.slice(0, 8)}…${c.id.slice(-4)}` : c.id}
                  </span>
                  {c.yellow_flag_count > 0 && (
                    <span className="ml-[6px] text-[9px] font-semibold px-[5px] py-[1px] rounded-[3px] bg-warn-muted text-warn-text">
                      YF
                    </span>
                  )}
                </td>
                <td className="px-[14px] py-[11px]">
                  <span
                    className={`inline-flex items-center text-[10px] font-semibold px-2 py-[3px] rounded-pill uppercase tracking-[0.4px] ${c.market === 'crypto' ? 'bg-accent-muted text-accent-text' : 'bg-gold-muted text-gold-text'}`}
                  >
                    {c.market}
                  </span>
                </td>
                <td className="px-[14px] py-[11px] text-text-secondary text-small">{c.source}</td>
                <td className="px-[14px] py-[11px]">
                  <div className="flex items-center gap-[9px]">
                    <span className="font-semibold w-[26px] mono">
                      {c.composite_score.toFixed(0)}
                    </span>
                    <div className="flex-1 h-[5px] bg-bg-surface-2 rounded-pill overflow-hidden min-w-[50px]">
                      <div
                        className="h-full rounded-pill"
                        style={{
                          width: `${c.composite_score}%`,
                          background: 'linear-gradient(90deg, #2dd4bf, #d9a441)',
                        }}
                      />
                    </div>
                  </div>
                </td>
                <td
                  className={`px-[14px] py-[11px] text-right mono text-small ${c.cum_pnl_usd >= 0 ? 'text-pos-text' : 'text-neg-text'}`}
                >
                  {c.cum_pnl_usd >= 0 ? '+' : ''}$
                  {Math.abs(c.cum_pnl_usd).toLocaleString('en-US', { maximumFractionDigits: 0 })}
                </td>
                <td className="px-[14px] py-[11px] text-right mono text-small">
                  {c.peak_drawdown.toFixed(1)}%
                </td>
                <td className="px-[14px] py-[11px] text-right mono text-small">
                  {(c.overall_win_rate * 100).toFixed(0)}%
                </td>
                <td className="px-[14px] py-[11px]">
                  <span
                    className={`inline-flex text-[10px] font-semibold px-2 py-[3px] rounded-pill uppercase tracking-[0.4px] ${CONSISTENCY_PILL[c.win_rate_trend] ?? CONSISTENCY_PILL.stable}`}
                  >
                    {c.win_rate_trend}
                  </span>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={9} className="text-center py-12 text-text-tertiary text-small">
                  No candidates match the current filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-3 text-micro text-text-tertiary bg-bg-sunken border border-border-subtle rounded-md px-3 py-[10px] flex gap-2 items-start">
        <svg
          className="w-[14px] h-[14px] flex-shrink-0 mt-[1px]"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <circle cx="12" cy="12" r="10" />
          <path d="M12 16v-4M12 8h.01" />
        </svg>
        <span>
          Click any row to open the full candidate profile. Top 5 shortlist marked in gold. Sort on
          any numeric column.
        </span>
      </div>
    </div>
  )
}
