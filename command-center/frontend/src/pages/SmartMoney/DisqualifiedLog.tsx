import { useState } from 'react'
import type { DisqualifiedCandidate } from '@/types'

// ── Reason categorisation ──────────────────────────────────────────────────────

type ReasonCategory = 'win_rate' | 'activity' | 'drawdown' | 'concentration' | 'api_error' | 'other'

function categorizeReason(reason: string): ReasonCategory {
  const r = reason.toLowerCase()
  if (r.startsWith('api error') || r.includes('all 3 attempts') || r.includes('api error'))
    return 'api_error'
  if (r.includes('drawdown')) return 'drawdown'
  if (r.includes('single trade') || r.includes('concentrat') || r.includes('pnl share'))
    return 'concentration'
  if (
    r.includes('win rate') ||
    r.includes('strike') ||
    r.includes('yellow') ||
    r.includes('red flag')
  )
    return 'win_rate'
  if (
    r.includes('active week') ||
    r.includes('trading span') ||
    r.includes('window starting') ||
    r.includes('trade count') ||
    r.includes('instruments') ||
    r.includes('hold hour') ||
    r.includes('matched trades') ||
    r.includes('matched trade')
  )
    return 'activity'
  if (r.includes('net unprofitable') || r.includes('total pnl')) return 'drawdown'
  return 'other'
}

const CATEGORY_LABELS: Record<ReasonCategory, string> = {
  win_rate: 'Win Rate',
  activity: 'Activity',
  drawdown: 'Drawdown',
  concentration: 'Concentration',
  api_error: 'API Error',
  other: 'Other',
}

const CATEGORY_BADGE: Record<ReasonCategory, string> = {
  win_rate: 'bg-neg-muted text-neg-text',
  activity: 'bg-accent-muted text-accent-text',
  drawdown: 'bg-neg-muted text-neg-text',
  concentration: 'bg-gold-muted text-gold-text',
  api_error: 'bg-warn-muted text-warn-text',
  other: 'bg-bg-surface-2 text-text-secondary',
}

/** Clean up machine-readable timestamps in reason strings for display. */
function formatReason(reason: string): string {
  // "Window starting 1753650641019 has only 1 active weeks (need 2)"
  //  → "Window (Jul 27, 2025): only 1 active weeks (need 2)"
  return reason.replace(
    /Window starting (\d{13}) has only (\d+) active weeks \(need (\d+)\)/,
    (_, ts, actual, needed) => {
      const date = new Date(parseInt(ts)).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
      return `Window (${date}): ${actual} active weeks — needed ${needed}`
    }
  )
}

/** Build a Hyperliquid explorer link for an address. Returns null for unknown sources. */
function walletLink(id: string, source: string): string | null {
  if (source === 'hyperliquid') return `https://app.hyperliquid.xyz/explorer/address/${id}`
  return null
}

// ── Filter pill logic ─────────────────────────────────────────────────────────

type FilterKey =
  'All reasons' | 'Win rate' | 'Activity' | 'Drawdown' | 'Concentration' | 'API errors'

const REASON_FILTERS: FilterKey[] = [
  'All reasons',
  'Win rate',
  'Activity',
  'Drawdown',
  'Concentration',
  'API errors',
]

function matchesFilter(reason: string, filter: FilterKey): boolean {
  if (filter === 'All reasons') return true
  const cat = categorizeReason(reason)
  if (filter === 'Win rate') return cat === 'win_rate'
  if (filter === 'Activity') return cat === 'activity'
  if (filter === 'Drawdown') return cat === 'drawdown'
  if (filter === 'Concentration') return cat === 'concentration'
  if (filter === 'API errors') return cat === 'api_error'
  return true
}

// ── Component ─────────────────────────────────────────────────────────────────

export function DisqualifiedLog({ disqualified }: { disqualified: DisqualifiedCandidate[] }) {
  const [reasonFilter, setReasonFilter] = useState<FilterKey>('All reasons')
  const [search, setSearch] = useState('')

  const filtered = disqualified
    .filter((d) => matchesFilter(d.reason, reasonFilter))
    .filter((d) => !search || d.id.toLowerCase().includes(search.toLowerCase()))

  // Category counts for filter chips
  const counts: Record<FilterKey, number> = {
    'All reasons': disqualified.length,
    'Win rate': disqualified.filter((d) => categorizeReason(d.reason) === 'win_rate').length,
    Activity: disqualified.filter((d) => categorizeReason(d.reason) === 'activity').length,
    Drawdown: disqualified.filter((d) => categorizeReason(d.reason) === 'drawdown').length,
    Concentration: disqualified.filter((d) => categorizeReason(d.reason) === 'concentration')
      .length,
    'API errors': disqualified.filter((d) => categorizeReason(d.reason) === 'api_error').length,
  }

  return (
    <div>
      <div className="flex gap-2 mb-3 items-center flex-wrap">
        <div className="flex bg-bg-surface border border-border-subtle rounded-md overflow-hidden">
          {REASON_FILTERS.map((f) => (
            <span
              key={f}
              onClick={() => setReasonFilter(f)}
              className={`text-micro px-3 py-[6px] cursor-pointer select-none transition-colors duration-[100ms] flex items-center gap-[5px] ${reasonFilter === f ? 'bg-accent-muted text-text-primary' : 'text-text-secondary hover:bg-bg-hover'}`}
            >
              {f}
              {counts[f] > 0 && (
                <span
                  className={`text-[9px] font-semibold tabular-nums ${reasonFilter === f ? 'text-accent' : 'text-text-tertiary'}`}
                >
                  {counts[f]}
                </span>
              )}
            </span>
          ))}
        </div>
        <div className="relative">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter disqualified IDs"
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
          {filtered.length.toLocaleString()} of {disqualified.length.toLocaleString()}
        </span>
      </div>

      <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              {['Wallet / account', 'Market', 'Source', 'Stage', 'Disqualification reason'].map(
                (h) => (
                  <th
                    key={h}
                    className="text-left text-[10px] font-semibold uppercase tracking-[0.7px] text-text-tertiary px-[14px] py-[10px] bg-bg-surface-2 border-b border-border-subtle whitespace-nowrap"
                  >
                    {h}
                  </th>
                )
              )}
            </tr>
          </thead>
          <tbody>
            {filtered.map((d, i) => {
              const link = walletLink(d.id, d.source)
              const cat = categorizeReason(d.reason)
              const displayReason = formatReason(d.reason)

              return (
                <tr
                  key={i}
                  className="border-b border-border-subtle last:border-0 hover:bg-bg-hover/40 transition-colors duration-[80ms]"
                >
                  {/* Wallet address — clickable link when source supports it */}
                  <td className="px-[14px] py-[11px] font-mono text-[11px]">
                    {link ? (
                      <a
                        href={link}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-accent hover:text-accent-hover transition-colors duration-[100ms]"
                        title={d.id}
                      >
                        {d.id.slice(0, 10)}…{d.id.slice(-6)}
                      </a>
                    ) : (
                      <span className="text-text-secondary" title={d.id}>
                        {d.id.length > 20 ? `${d.id.slice(0, 10)}…${d.id.slice(-6)}` : d.id}
                      </span>
                    )}
                  </td>

                  {/* Market badge */}
                  <td className="px-[14px] py-[11px]">
                    <span
                      className={`inline-flex text-[10px] font-semibold px-2 py-[3px] rounded-pill uppercase tracking-[0.4px] ${d.market === 'crypto' ? 'bg-accent-muted text-accent-text' : 'bg-gold-muted text-gold-text'}`}
                    >
                      {d.market}
                    </span>
                  </td>

                  <td className="px-[14px] py-[11px] text-text-secondary text-small">{d.source}</td>
                  <td className="px-[14px] py-[11px] font-mono text-[11px] text-text-tertiary">
                    {d.stage}
                  </td>

                  {/* Reason: category badge + truncated reason text */}
                  <td className="px-[14px] py-[11px] min-w-0">
                    <div className="flex flex-col gap-[4px]">
                      <span
                        className={`inline-flex self-start text-[10px] font-semibold px-[8px] py-[2px] rounded-pill uppercase tracking-[0.4px] ${CATEGORY_BADGE[cat]}`}
                      >
                        {CATEGORY_LABELS[cat]}
                      </span>
                      <span
                        className="text-[11px] text-text-secondary max-w-[340px] truncate block"
                        title={d.reason}
                      >
                        {displayReason}
                      </span>
                    </div>
                  </td>
                </tr>
              )
            })}
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
          Nothing is silently dropped — every removed candidate is logged with its reason and the
          stage that removed it. Hover any reason for the full text.
        </span>
      </div>
    </div>
  )
}
