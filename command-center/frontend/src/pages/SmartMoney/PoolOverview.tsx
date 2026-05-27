import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
} from 'recharts'
import type { SmartMoneyRun } from '@/types'
import { StatCard } from '@/components/StatCard'

function FunnelChart({ funnel }: { funnel: SmartMoneyRun['funnel'] }) {
  const max = funnel[0]?.count_in ?? 1
  return (
    <div className="space-y-[11px]">
      {funnel.map((stage, i) => {
        const count = i === 0 ? stage.count_in : stage.count_out
        const pct = Math.max(2, Math.round((count / max) * 100))
        const isLast = i === funnel.length - 1
        return (
          <div key={stage.label}>
            <div className="flex justify-between text-micro text-text-secondary mb-1">
              <span>{stage.label}</span>
              <b className="text-text-primary mono">{count.toLocaleString()}</b>
            </div>
            <div className="h-4 bg-bg-surface-2 rounded-sm overflow-hidden">
              <div
                className="h-full rounded-sm transition-all duration-[600ms]"
                style={{
                  width: `${pct}%`,
                  background: isLast
                    ? 'linear-gradient(90deg, #d9a441, #e8bf6f)'
                    : 'linear-gradient(90deg, #2dd4bf, #5eead4)',
                }}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}

const DONUT_COLORS = ['#2dd4bf', '#d9a441']

export function PoolOverview({ run }: { run: SmartMoneyRun }) {
  const sourceData = Object.entries(run.by_source).map(([name, value]) => ({ name, value }))
  const marketData = Object.entries(run.by_market).map(([name, value]) => ({ name, value }))
  const total = Object.values(run.by_market).reduce((a, b) => a + b, 0)

  return (
    <div className="space-y-3">
      {/* Stat cards */}
      <div className="grid grid-cols-4 gap-[10px]">
        <StatCard
          label="API Scanned"
          value={run.total_scanned.toLocaleString()}
          sub={`top candidates, ${Object.keys(run.by_source).length} sources`}
        />
        <StatCard
          label="Qualified"
          value={run.total_qualified.toLocaleString()}
          sub={total > 0 ? `${((run.total_qualified / run.total_scanned) * 100).toFixed(2)}% pass rate` : '—'}
          subVariant="pos"
        />
        <StatCard
          label="Crypto"
          value={(run.by_market.crypto ?? 0).toLocaleString()}
          sub={Object.keys(run.by_source).filter(s => !['myfxbook', 'fx_blue'].includes(s)).join(' · ')}
        />
        <StatCard
          label="Forex"
          value={(run.by_market.forex ?? 0).toLocaleString()}
          sub={Object.keys(run.by_source).filter(s => ['myfxbook', 'fx_blue'].includes(s)).join(' · ')}
        />
      </div>

      {/* Funnel + source charts */}
      <div className="grid grid-cols-[1.45fr_1fr] gap-3">
        <div className="bg-bg-surface border border-border-subtle rounded-lg p-4">
          <div className="flex items-center mb-[14px]">
            <span className="text-[13px] font-semibold">Filter funnel</span>
            <span className="text-micro text-text-tertiary ml-auto">attrition per stage</span>
          </div>
          <FunnelChart funnel={run.funnel} />
        </div>

        <div className="bg-bg-surface border border-border-subtle rounded-lg p-4">
          <div className="text-[13px] font-semibold mb-[14px]">Candidates by source</div>
          <ResponsiveContainer width="100%" height={120}>
            <BarChart data={sourceData} layout="vertical" margin={{ left: 0, right: 8, top: 0, bottom: 0 }}>
              <XAxis type="number" hide />
              <YAxis type="category" dataKey="name" width={90} tick={{ fontSize: 11, fill: '#9a9eb0' }} />
              <Tooltip
                contentStyle={{ background: '#181a20', border: '1px solid #313542', borderRadius: 8, fontSize: 11 }}
                cursor={{ fill: '#252833' }}
              />
              <Bar dataKey="value" fill="#2dd4bf" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>

          <div className="text-[13px] font-semibold mt-[18px] mb-3">Market split</div>
          <div className="flex items-center gap-4">
            <PieChart width={84} height={84}>
              <Pie data={marketData} cx={42} cy={42} innerRadius={24} outerRadius={38} dataKey="value" stroke="none">
                {marketData.map((_, i) => (
                  <Cell key={i} fill={DONUT_COLORS[i % DONUT_COLORS.length]} />
                ))}
              </Pie>
            </PieChart>
            <div className="text-micro space-y-[6px]">
              {marketData.map((m, i) => (
                <div key={m.name} className="flex items-center gap-[7px]">
                  <span className="w-[7px] h-[7px] rounded-full flex-shrink-0" style={{ background: DONUT_COLORS[i] }} />
                  <span className="capitalize text-text-secondary">{m.name}</span>
                  <b className="text-text-primary">{m.value}</b>
                  <span className="text-text-tertiary">{total > 0 ? `${Math.round((m.value / total) * 100)}%` : ''}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export function PoolOverviewEmpty() {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-4 gap-[10px]">
        {['Scanned', 'Qualified', 'Crypto', 'Forex'].map(l => (
          <StatCard key={l} label={l} value="—" sub="No run selected" />
        ))}
      </div>
      <div className="bg-bg-surface border border-border-subtle rounded-lg p-8 text-center text-text-tertiary text-small">
        No pipeline runs found. Run the smart money pipeline to see results here.
      </div>
    </div>
  )
}
