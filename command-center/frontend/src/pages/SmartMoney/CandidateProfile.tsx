import { ArrowLeft } from 'lucide-react'
import {
  AreaChart, Area, LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from 'recharts'
import type { Candidate } from '@/types'
import { StatCard } from '@/components/StatCard'

const SCORE_LABELS: Record<string, string> = {
  win_rate_consistency:    'Win-rate consistency',
  risk_adjusted_return:    'Risk-adjusted return',
  exit_efficiency:         'Exit efficiency',
  trade_frequency:         'Trade frequency',
  instrument_consistency:  'Instrument consistency',
  instrument_day_consistency: 'Instrument consistency',
}

export function CandidateProfile({ candidate, onBack }: { candidate: Candidate; onBack: () => void }) {
  const balanceData = candidate.monthly_balance.map(m => ({ month: m.month, value: m.value }))
  const winRateData = candidate.monthly_win_rate.map(m => ({ month: m.month, value: m.value * 100 }))

  return (
    <div className="space-y-3">
      {/* Back */}
      <button onClick={onBack} className="flex items-center gap-[6px] text-small text-text-secondary hover:text-text-primary transition-colors mb-2">
        <ArrowLeft size={14} />
        Back to rankings
      </button>

      <div className="bg-bg-surface border border-border-subtle rounded-lg p-4">
        {/* Header */}
        <div className="flex items-center gap-[14px] pb-4 mb-4 border-b border-border-subtle">
          <div className="w-[46px] h-[46px] rounded-[11px] flex-shrink-0 flex items-center justify-center font-bold text-[15px] text-white"
               style={{ background: 'linear-gradient(135deg, #2dd4bf, #0d9488)' }}>
            {candidate.market === 'crypto' ? '0x' : candidate.source.slice(0, 2).toUpperCase()}
          </div>
          <div>
            <div className="font-mono text-[13px] font-medium">
              {candidate.id.length > 20 ? `${candidate.id.slice(0, 10)}…${candidate.id.slice(-6)}` : candidate.id}
            </div>
            <div className="text-micro text-text-secondary mt-[2px] flex gap-2 items-center">
              <span className={`inline-flex text-[10px] font-semibold px-2 py-[3px] rounded-pill uppercase tracking-[0.4px] ${candidate.market === 'crypto' ? 'bg-accent-muted text-accent-text' : 'bg-gold-muted text-gold-text'}`}>
                {candidate.market}
              </span>
              <span>{candidate.source}</span>
              {candidate.is_shortlist && (
                <span className="inline-flex text-[10px] font-semibold px-2 py-[3px] rounded-pill uppercase tracking-[0.4px] bg-gold-muted text-gold-text">
                  Top 5 shortlist
                </span>
              )}
              {candidate.yellow_flags.map((f, i) => (
                <span key={i} className="inline-flex text-[10px] font-semibold px-2 py-[3px] rounded-pill bg-warn-muted text-warn-text">⚑ {f}</span>
              ))}
            </div>
          </div>
          <div className="ml-auto text-right">
            <div className="text-[30px] font-bold tracking-[-1px] text-gold-text mono">{candidate.composite_score.toFixed(0)}</div>
            <div className="text-[10px] text-text-tertiary uppercase tracking-[0.7px]">Composite · rank {candidate.rank}</div>
          </div>
        </div>

        {/* Balance stats */}
        <div className="grid grid-cols-5 gap-[10px] mb-[18px]">
          <StatCard label="Start" value={`$${(candidate.starting_balance / 1000).toFixed(1)}k`} />
          <StatCard label="End" value={`$${(candidate.ending_balance / 1000).toFixed(1)}k`} />
          <StatCard label="Net growth" value={`+${candidate.net_growth_pct.toFixed(0)}%`} subVariant="pos" />
          <StatCard label="Peak DD" value={`${candidate.peak_drawdown.toFixed(1)}%`} />
          <StatCard label="Trades" value={candidate.trade_count.toLocaleString()} />
        </div>

        {/* Sparklines */}
        <div className="grid grid-cols-2 gap-3 mb-3">
          <div className="bg-bg-sunken border border-border-subtle rounded-lg p-4">
            <div className="flex items-center mb-[14px]">
              <span className="text-[13px] font-semibold">Balance progression</span>
              <span className="text-micro text-text-tertiary ml-auto">monthly</span>
            </div>
            <ResponsiveContainer width="100%" height={90}>
              <AreaChart data={balanceData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id="balGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#34d399" stopOpacity={0.15}/>
                    <stop offset="95%" stopColor="#34d399" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <XAxis dataKey="month" hide />
                <YAxis hide />
                <Tooltip contentStyle={{ background: '#181a20', border: '1px solid #313542', borderRadius: 8, fontSize: 11 }} />
                <Area type="monotone" dataKey="value" stroke="#34d399" fill="url(#balGrad)" strokeWidth={2} dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <div className="bg-bg-sunken border border-border-subtle rounded-lg p-4">
            <div className="flex items-center mb-[14px]">
              <span className="text-[13px] font-semibold">Monthly win rate</span>
              <span className="text-micro text-text-tertiary ml-auto">80% threshold</span>
            </div>
            <ResponsiveContainer width="100%" height={90}>
              <LineChart data={winRateData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                <XAxis dataKey="month" hide />
                <YAxis hide domain={[70, 100]} />
                <Tooltip contentStyle={{ background: '#181a20', border: '1px solid #313542', borderRadius: 8, fontSize: 11 }} formatter={(v: number) => [`${v.toFixed(1)}%`]} />
                <ReferenceLine y={80} stroke="#d9a441" strokeDasharray="3 3" strokeOpacity={0.7} />
                <Line type="monotone" dataKey="value" stroke="#2dd4bf" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Score breakdown + behavioral */}
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-bg-sunken border border-border-subtle rounded-lg p-4">
            <div className="text-[13px] font-semibold mb-[14px]">Score breakdown</div>
            <div className="space-y-[9px]">
              {Object.entries(candidate.score_breakdown).map(([key, val]) => (
                <div key={key} className="flex items-center gap-[10px] text-micro">
                  <span className="w-[135px] flex-shrink-0 text-text-secondary">{SCORE_LABELS[key] ?? key}</span>
                  <div className="flex-1 h-[7px] bg-bg-surface-2 rounded-pill overflow-hidden">
                    <div className="h-full bg-accent rounded-pill" style={{ width: `${Math.min(100, val)}%` }} />
                  </div>
                  <span className="w-[30px] text-right font-semibold mono">{val.toFixed(0)}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="bg-bg-sunken border border-border-subtle rounded-lg p-4">
            <div className="text-[13px] font-semibold mb-[14px]">Behavioral pattern</div>
            <table className="w-full text-micro">
              <tbody>
                <tr>
                  <td className="text-text-secondary py-[5px]">Preferred days</td>
                  <td className="text-right py-[5px]">{candidate.preferred_days.slice(0, 3).map(d => d.label).join(', ')}</td>
                </tr>
                <tr>
                  <td className="text-text-secondary py-[5px]">Top instrument</td>
                  <td className="text-right py-[5px]">
                    {candidate.preferred_instruments[0]
                      ? `${candidate.preferred_instruments[0].label}${candidate.preferred_instruments[0].win_rate != null ? ` · ${(candidate.preferred_instruments[0].win_rate * 100).toFixed(0)}% WR` : ''}`
                      : '—'}
                  </td>
                </tr>
                <tr>
                  <td className="text-text-secondary py-[5px]">Entry time</td>
                  <td className="text-right py-[5px]">{candidate.typical_entry_time || '—'}</td>
                </tr>
                <tr>
                  <td className="text-text-secondary py-[5px]">Avg hold</td>
                  <td className="text-right py-[5px]">{candidate.avg_hold_time_hours.toFixed(1)} hours</td>
                </tr>
                <tr>
                  <td className="text-text-secondary py-[5px]">Exit efficiency</td>
                  <td className="text-right py-[5px]">
                    <span className="inline-flex text-[10px] font-semibold px-2 py-[3px] rounded-pill bg-pos-muted text-pos-text">
                      {candidate.exit_efficiency.toFixed(2)}
                    </span>
                  </td>
                </tr>
                {candidate.preferred_session && (
                  <tr>
                    <td className="text-text-secondary py-[5px]">Session</td>
                    <td className="text-right py-[5px]">{candidate.preferred_session}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}
