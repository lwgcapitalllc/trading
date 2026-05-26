import { useState } from 'react'
import { Play, Download } from 'lucide-react'
import {
  useSmartMoneyRuns, useSmartMoneyRun, useCandidates,
  useDisqualified, useSmartMoneyConfig, useConfigGitStatus, useSaveConfig,
} from '@/hooks/useSmartMoney'
import { PoolOverview, PoolOverviewEmpty } from './PoolOverview'
import { Rankings } from './Rankings'
import { CandidateProfile } from './CandidateProfile'
import { DisqualifiedLog } from './DisqualifiedLog'
import { Config } from './Config'
import type { Candidate } from '@/types'

type Tab = 'overview' | 'rankings' | 'profile' | 'disqualified' | 'config'

const TABS: Array<{ id: Tab; label: string }> = [
  { id: 'overview',     label: 'Pool overview' },
  { id: 'rankings',     label: 'Rankings' },
  { id: 'profile',      label: 'Candidate profile' },
  { id: 'disqualified', label: 'Disqualified' },
  { id: 'config',       label: 'Config' },
]

export function SmartMoney() {
  const [tab, setTab] = useState<Tab>('overview')
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [selectedCandidate, setSelectedCandidate] = useState<Candidate | null>(null)

  const { data: runs } = useSmartMoneyRuns()
  const activeRunId = selectedRunId ?? runs?.[0]?.run_id ?? null

  const { data: run, isLoading: runLoading } = useSmartMoneyRun(activeRunId)
  const { data: candidates, isLoading: candLoading } = useCandidates(activeRunId)
  const { data: disqualified } = useDisqualified(activeRunId)
  const { data: config, isLoading: cfgLoading } = useSmartMoneyConfig()
  const { data: gitStatus } = useConfigGitStatus()
  const { mutate: saveConfig, isPending: saving, error: saveErr } = useSaveConfig()

  const handleSelectCandidate = (c: Candidate) => {
    setSelectedCandidate(c)
    setTab('profile')
  }

  const runDate = run?.generated_at
    ? new Date(run.generated_at).toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' })
    : null

  return (
    <div>
      {/* Page header */}
      <div className="flex items-end gap-3 mb-[18px]">
        <h1 className="text-h1 font-semibold">Smart Money</h1>
        {runDate && <span className="text-[12px] text-text-tertiary pb-[2px]">{runDate}</span>}
        <div className="ml-auto flex gap-2">
          {/* Run selector */}
          {runs && runs.length > 0 && (
            <select
              value={activeRunId ?? ''}
              onChange={e => setSelectedRunId(e.target.value)}
              className="bg-bg-surface border border-border-default rounded-md px-3 py-[6px] text-small text-text-primary focus:outline-none focus:border-accent"
            >
              {runs.map(r => (
                <option key={r.run_id} value={r.run_id}>
                  {new Date(r.generated_at).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })} · {r.total_qualified} qualified
                </option>
              ))}
            </select>
          )}
          <button className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small border border-border-default bg-bg-surface text-text-primary hover:bg-bg-hover transition-colors duration-[120ms]">
            <Download size={14} />
            Export
          </button>
          <button className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small font-medium bg-accent border border-accent text-[#06201d] hover:bg-accent-hover transition-colors duration-[120ms]">
            <Play size={14} />
            Run pipeline
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-[2px] mb-[18px] border-b border-border-subtle">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`text-small px-[13px] py-2 cursor-pointer border-b-2 -mb-px transition-colors duration-[120ms] ${
              tab === t.id
                ? 'text-text-primary border-accent'
                : 'text-text-secondary border-transparent hover:text-text-primary'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === 'overview' && (
        runLoading
          ? <div className="text-text-tertiary text-small py-12 text-center">Loading…</div>
          : run
          ? <PoolOverview run={run} />
          : <PoolOverviewEmpty />
      )}

      {tab === 'rankings' && (
        candLoading
          ? <div className="text-text-tertiary text-small py-12 text-center">Loading candidates…</div>
          : candidates && candidates.length > 0
          ? <Rankings candidates={candidates} onSelect={handleSelectCandidate} />
          : <div className="text-center py-12 text-text-tertiary text-small">
              No candidates found in this run.
            </div>
      )}

      {tab === 'profile' && (
        selectedCandidate
          ? <CandidateProfile candidate={selectedCandidate} onBack={() => setTab('rankings')} />
          : <div className="text-center py-12 text-text-tertiary text-small">
              Select a candidate from the Rankings tab to view their full profile.
            </div>
      )}

      {tab === 'disqualified' && (
        disqualified
          ? <DisqualifiedLog disqualified={disqualified} />
          : <div className="text-center py-12 text-text-tertiary text-small">
              No disqualified log available for this run.
            </div>
      )}

      {tab === 'config' && (
        cfgLoading
          ? <div className="text-text-tertiary text-small py-12 text-center">Loading config…</div>
          : config
          ? <Config
              config={config}
              gitStatus={gitStatus}
              onSave={saveConfig}
              isSaving={saving}
              saveError={saveErr ? String(saveErr) : null}
            />
          : <div className="text-center py-12 text-neg-text text-small">
              Could not load pipeline config. Check that the config file path in Settings is correct.
            </div>
      )}
    </div>
  )
}
