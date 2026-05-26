import { useState, useRef, useEffect } from 'react'
import { Play, Download } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useSmartMoneyRuns, useSmartMoneyRun, useCandidates,
  useDisqualified, useSmartMoneyConfig, useConfigGitStatus, useSaveConfig,
  useRunProgress,
} from '@/hooks/useSmartMoney'
import { PoolOverview, PoolOverviewEmpty } from './PoolOverview'
import { Rankings } from './Rankings'
import { CandidateProfile } from './CandidateProfile'
import { DisqualifiedLog } from './DisqualifiedLog'
import { Config } from './Config'
import type { Candidate, RunProgress } from '@/types'

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return `${m}m ${s}s`
}

function RunProgressBar({ progress }: { progress: RunProgress }) {
  const isRunning = progress.status === 'running'
  const isDone = progress.status === 'complete'
  const isError = progress.status === 'error'

  return (
    <div className={`mb-[18px] rounded-lg border p-4 ${
      isError ? 'bg-neg-muted border-neg-muted' :
      isDone  ? 'bg-pos-muted border-pos-muted' :
                'bg-bg-surface border-border-subtle'
    }`}>
      <div className="flex items-center justify-between mb-[10px]">
        <div className="flex items-center gap-2">
          {isRunning && <span className="w-[7px] h-[7px] rounded-full bg-accent animate-pulse flex-shrink-0" />}
          {isDone    && <span className="w-[7px] h-[7px] rounded-full bg-pos flex-shrink-0" />}
          {isError   && <span className="w-[7px] h-[7px] rounded-full bg-neg flex-shrink-0" />}
          <span className="text-small font-semibold">
            {progress.stage_name || `Stage ${progress.stage}`}
          </span>
          {progress.phase && progress.phase !== 'complete' && progress.phase !== 'error' && (
            <span className="text-micro text-text-tertiary">· {progress.phase}</span>
          )}
        </div>
        <div className="flex items-center gap-3 text-micro text-text-tertiary">
          {progress.wallets_total > 0 && (
            <span className="font-mono">{progress.wallets_scanned} / {progress.wallets_total} wallets</span>
          )}
          <span>{formatElapsed(progress.elapsed_seconds)}</span>
          <span className="font-mono font-medium text-text-secondary">{progress.pct}%</span>
        </div>
      </div>

      <div className="h-[5px] bg-bg-surface-2 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-[width] duration-500 ease-out ${
            isError ? 'bg-neg' : isDone ? 'bg-pos' : 'bg-accent'
          }`}
          style={{ width: `${progress.pct}%` }}
        />
      </div>

      <div className="flex items-center gap-4 mt-2 text-micro text-text-tertiary">
        {progress.qualified_so_far > 0 && (
          <span className="text-pos-text font-medium">{progress.qualified_so_far} qualified</span>
        )}
        {progress.disqualified_so_far > 0 && (
          <span>{progress.disqualified_so_far} disqualified</span>
        )}
        {progress.message && (
          <span className="ml-auto truncate max-w-[300px]">{progress.message}</span>
        )}
      </div>
    </div>
  )
}

type Tab = 'overview' | 'rankings' | 'profile' | 'disqualified' | 'config'

const TABS: Array<{ id: Tab; label: string }> = [
  { id: 'overview',     label: 'Pool overview' },
  { id: 'rankings',     label: 'Rankings' },
  { id: 'profile',      label: 'Candidate profile' },
  { id: 'disqualified', label: 'Disqualified' },
  { id: 'config',       label: 'Config' },
]

export function SmartMoney() {
  const qc = useQueryClient()
  const [tab, setTab] = useState<Tab>('overview')
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [selectedCandidate, setSelectedCandidate] = useState<Candidate | null>(null)

  const { data: progress } = useRunProgress()
  const prevStatus = useRef<string | undefined>(undefined)
  useEffect(() => {
    if (prevStatus.current === 'running' && progress?.status === 'complete') {
      qc.invalidateQueries({ queryKey: ['smart-money', 'runs'] })
    }
    prevStatus.current = progress?.status
  }, [progress?.status, qc])

  const showProgress = progress != null && progress.status !== 'idle'

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

      {showProgress && <RunProgressBar progress={progress} />}

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
