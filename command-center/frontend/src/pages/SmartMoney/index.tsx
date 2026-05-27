import { useState, useRef, useEffect } from 'react'
import { Play, Download } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useSmartMoneyRuns, useSmartMoneyRun, useCandidates,
  useDisqualified, useSmartMoneyConfig, useConfigGitStatus, useSaveConfig,
  useRunProgress, useRunPipeline, useStopPipeline,
} from '@/hooks/useSmartMoney'
import { PoolOverview, PoolOverviewEmpty } from './PoolOverview'
import { Rankings } from './Rankings'
import { CandidateProfile } from './CandidateProfile'
import { DisqualifiedLog } from './DisqualifiedLog'
import { Config } from './Config'
import type { Candidate, RunProgress, ScanEntry } from '@/types'

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return `${m}m ${s}s`
}

// ── ScannerTerminal ───────────────────────────────────────────────────────────

type FeedEntry = ScanEntry & { id: number }

function ScannerTerminal({ progress }: { progress: RunProgress }) {
  const isRunning = progress.status === 'running'
  const isDone    = progress.status === 'complete'
  const isError   = progress.status === 'error'

  // During the scan phase, show per-scan progress (wallets_scanned / wallets_total)
  // instead of overall pipeline %. The backend pct is designed for a multi-stage
  // pipeline (scan = first 10%), which is misleading when only Stage 1 runs.
  const isScanPhase = isRunning && progress.wallets_total > 0
  const displayPct = isScanPhase
    ? Math.round(progress.wallets_scanned / progress.wallets_total * 100)
    : isDone ? 100
    : progress.pct

  // Live elapsed counter — ticks from started_at every second so it's smooth
  // even between 1s backend polls.
  const [liveElapsed, setLiveElapsed] = useState(progress.elapsed_seconds)
  useEffect(() => {
    if (!isRunning || !progress.started_at) {
      setLiveElapsed(progress.elapsed_seconds)
      return
    }
    const startMs = new Date(progress.started_at).getTime()
    const tick = () => setLiveElapsed((Date.now() - startMs) / 1000)
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [isRunning, progress.started_at, progress.elapsed_seconds])

  // ── Address feed animation ───────────────────────────────────────────────
  // Backend delivers recent_addresses every 1s poll.  We drain them into the
  // visual feed one-by-one at 90ms each so the terminal feels like real-time
  // streaming rather than a batch jump.
  const [feed, setFeed] = useState<FeedEntry[]>([])
  const seenRef      = useRef(new Set<string>())
  const drainQueue   = useRef<ScanEntry[]>([])
  const drainingRef  = useRef(false)
  const feedIdRef    = useRef(0)

  useEffect(() => {
    const incoming = progress.recent_addresses ?? []
    const newOnes  = incoming.filter(e => !seenRef.current.has(e.a))
    if (!newOnes.length) return

    drainQueue.current.push(...newOnes)
    if (drainingRef.current) return       // already draining — let it continue

    drainingRef.current = true
    const step = () => {
      const entry = drainQueue.current.shift()
      if (!entry) { drainingRef.current = false; return }
      seenRef.current.add(entry.a)
      setFeed(prev => [{ ...entry, id: feedIdRef.current++ }, ...prev.slice(0, 17)])
      setTimeout(step, 90)
    }
    step()
  }, [progress.recent_addresses])

  // Clear feed when a new run starts (phase resets to "starting")
  useEffect(() => {
    if (progress.phase === 'starting') {
      setFeed([])
      seenRef.current.clear()
      drainQueue.current = []
      drainingRef.current = false
    }
  }, [progress.phase])

  // Computed stats
  const scanRate  = liveElapsed > 1 ? progress.wallets_scanned / liveElapsed : 0
  const isScan    = isRunning && (progress.phase === 'scanning wallets' || feed.length > 0)
  const showStats = progress.wallets_total > 0 || isDone || feed.length > 0

  // Border / bg colour based on state
  const wrapClass = isError
    ? 'border-neg bg-neg-muted'
    : isDone
    ? 'border-pos/40 bg-pos-muted'
    : 'border-border-default bg-bg-sunken'

  return (
    <div className={`mb-[18px] rounded-lg border overflow-hidden ${wrapClass}`}>

      {/* ── Header row ──────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-4 py-[10px] border-b border-border-subtle">
        <div className="flex items-center gap-[10px]">
          {isRunning && (
            <span className="relative flex h-[8px] w-[8px]">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-60" />
              <span className="relative inline-flex rounded-full h-[8px] w-[8px] bg-accent" />
            </span>
          )}
          {isDone  && <span className="w-[8px] h-[8px] rounded-full bg-pos flex-shrink-0" />}
          {isError && <span className="w-[8px] h-[8px] rounded-full bg-neg flex-shrink-0" />}
          <span className="text-small font-semibold font-mono tracking-wide uppercase">
            {progress.stage_name || `Stage ${progress.stage}`}
          </span>
          {progress.phase && !['complete', 'error', 'starting'].includes(progress.phase) && (
            <span className="text-micro text-text-tertiary font-mono">
              · {progress.phase}
            </span>
          )}
          {isDone && (
            <span className="text-micro text-pos font-mono">· run complete</span>
          )}
        </div>
        <div className="flex items-center gap-4 font-mono text-micro">
          <span className="text-text-tertiary tabular-nums">{formatElapsed(liveElapsed)}</span>
          <span
            className={`font-semibold tabular-nums ${
              isDone
                ? 'text-pos drop-shadow-glow-pos'
                : isError
                ? 'text-neg drop-shadow-glow-neg'
                : 'text-accent drop-shadow-glow-accent'
            }`}
          >
            {displayPct}%
          </span>
        </div>
      </div>

      {/* ── Feed body ───────────────────────────────────────────────────── */}
      <div className="relative h-[176px] overflow-hidden px-4 py-3 font-mono">

        {/* Scanline sweep — subtle horizontal glint during scan phase */}
        {isScan && (
          <div className="absolute inset-x-0 h-[1px] bg-gradient-to-r from-transparent via-accent/30 to-transparent animate-scanline pointer-events-none z-10" />
        )}

        {isScan ? (
          /* ── Matrix address feed ────────────────────────────────────── */
          <div className="flex flex-col gap-[2px]">
            {/* Blinking cursor — "currently scanning" */}
            {isRunning && (
              <div className="flex items-center gap-3 text-[11px] text-text-secondary pb-[3px]">
                <span className="text-accent text-[10px]">▶</span>
                <span className="text-text-tertiary">scanning</span>
                <span className="text-accent animate-pulse leading-none">█</span>
              </div>
            )}
            {feed.map((entry, i) => {
              const isPass = entry.s === 'pass'
              // Older entries fade toward transparent
              const opacity = Math.max(0.15, 1 - i * 0.052)
              return (
                <div
                  key={entry.id}
                  className="flex items-center gap-[10px] text-[11px] animate-fadein"
                  style={{ opacity }}
                >
                  <span className="text-text-tertiary w-[18px] text-right text-[9px] tabular-nums select-none">
                    {feed.length - i}
                  </span>
                  <span className="text-text-secondary tracking-wide select-all">
                    {entry.a.slice(0, 10)}
                    <span className="text-text-tertiary">…</span>
                    {entry.a.slice(-6)}
                  </span>
                  {/* Dotted line fills the gap */}
                  <span className="flex-1 overflow-hidden">
                    <span className="block border-b border-dashed border-border-subtle" />
                  </span>
                  {isPass ? (
                    <span className="text-pos font-semibold tracking-widest text-[10px] drop-shadow-glow-pos">
                      PASS ✓
                    </span>
                  ) : (
                    <span className="text-text-tertiary tracking-widest text-[10px]">
                      fail
                    </span>
                  )}
                </div>
              )
            })}
          </div>
        ) : (
          /* ── Status view for non-scan phases ────────────────────────── */
          <div className="flex flex-col justify-center h-full gap-[8px]">
            <div className="flex items-center gap-[10px] text-[12px] font-mono">
              {isRunning && <span className="text-accent text-[10px]">▶</span>}
              {isDone    && <span className="text-pos">✓</span>}
              {isError   && <span className="text-neg">✗</span>}
              <span className={isError ? 'text-neg-text' : isDone ? 'text-pos-text' : 'text-text-secondary'}>
                {progress.message || (isDone ? 'Run complete' : progress.phase || 'Starting…')}
              </span>
              {isRunning && (
                <span className="text-accent animate-pulse leading-none">█</span>
              )}
            </div>
            {/* Show phase progress for profiling/scoring steps */}
            {isRunning && progress.wallets_total > 0 && !isScan && (
              <div className="text-[10px] text-text-tertiary font-mono tabular-nums">
                {progress.wallets_scanned.toLocaleString()} / {progress.wallets_total.toLocaleString()} wallets processed
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Stats bar ───────────────────────────────────────────────────── */}
      {showStats && (
        <div className="px-4 py-[7px] border-t border-border-subtle flex items-center gap-5 font-mono text-[11px] flex-wrap">
          {progress.wallets_total > 0 && (
            <span className="text-text-tertiary tabular-nums">
              <span className="text-text-secondary font-medium">
                {progress.wallets_scanned.toLocaleString()}
              </span>
              {' / '}
              {progress.wallets_total.toLocaleString()} wallets
            </span>
          )}
          {scanRate >= 0.5 && (
            <span className="text-text-tertiary tabular-nums">
              <span className="text-text-secondary">{scanRate.toFixed(1)}</span>
              {' '}wallets/sec
            </span>
          )}
          {progress.qualified_so_far > 0 && (
            <span className="text-pos tabular-nums drop-shadow-glow-pos">
              <span className="font-semibold">{progress.qualified_so_far}</span> qualified
            </span>
          )}
          {progress.disqualified_so_far > 0 && (
            <span className="text-text-tertiary tabular-nums">
              {progress.disqualified_so_far.toLocaleString()} eliminated
            </span>
          )}
          {isDone && progress.qualified_so_far === 0 && progress.disqualified_so_far === 0 && (
            <span className="text-pos-text text-[10px]">Run complete</span>
          )}
        </div>
      )}

      {/* ── Progress bar ────────────────────────────────────────────────── */}
      <div className="h-[3px] bg-bg-surface-2">
        <div
          className={`h-full transition-[width] duration-700 ease-out ${
            isError ? 'bg-neg' : isDone ? 'bg-pos' : 'bg-accent'
          }`}
          style={{ width: `${Math.max(displayPct, isRunning ? 1 : 0)}%` }}
        />
      </div>
    </div>
  )
}

// ── Main SmartMoney page ──────────────────────────────────────────────────────

type Tab = 'overview' | 'rankings' | 'profile' | 'disqualified' | 'config'

const TABS: Array<{ id: Tab; label: string }> = [
  { id: 'overview',     label: 'Pool overview' },
  { id: 'rankings',     label: 'Rankings' },
  { id: 'profile',      label: 'Candidate profile' },
  { id: 'disqualified', label: 'Disqualified' },
  { id: 'config',       label: 'Config' },
]

// Placeholder progress shown immediately after clicking "Run pipeline", before
// Python has had time to start and write a real progress.json (takes 10–15s).
const STARTING_PROGRESS: RunProgress = {
  run_id: '', status: 'running', stage: 1, stage_name: 'Hyperliquid scan',
  phase: 'starting', pct: 0, wallets_scanned: 0, wallets_total: 0,
  qualified_so_far: 0, disqualified_so_far: 0,
  message: 'Launching pipeline…', started_at: new Date().toISOString(),
  updated_at: null, elapsed_seconds: 0, recent_addresses: [],
}

export function SmartMoney() {
  const qc = useQueryClient()
  const [tab, setTab] = useState<Tab>('overview')
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [selectedCandidate, setSelectedCandidate] = useState<Candidate | null>(null)

  // isStarting: true from the moment "Run pipeline" is clicked until the backend
  // confirms the run is actually running. Prevents the terminal from flickering
  // back to "complete" while Python is starting up (10–15s).
  const [isStarting, setIsStarting] = useState(false)
  // profile: which config template to use when triggering a run
  const [profile, setProfile] = useState<'bot' | 'human'>('bot')

  const { data: progress } = useRunProgress()
  const prevStatus = useRef<string | undefined>(undefined)
  useEffect(() => {
    // Once the backend confirms running, the local starting placeholder is no longer needed
    if (progress?.status === 'running') setIsStarting(false)
    if (prevStatus.current === 'running' && progress?.status === 'complete') {
      qc.invalidateQueries({ queryKey: ['smart-money', 'runs'] })
    }
    prevStatus.current = progress?.status
  }, [progress?.status, qc])

  // Safety valve: clear isStarting after 90s regardless (in case pipeline never starts)
  useEffect(() => {
    if (!isStarting) return
    const t = setTimeout(() => setIsStarting(false), 90_000)
    return () => clearTimeout(t)
  }, [isStarting])

  // What the terminal should display: local starting placeholder until real data arrives
  const effectiveProgress = (isStarting && progress?.status !== 'running')
    ? STARTING_PROGRESS
    : progress

  const isLive = isStarting || progress?.status === 'running'
  const showProgress = effectiveProgress != null && effectiveProgress.status !== 'idle'

  const { data: runs } = useSmartMoneyRuns()
  const activeRunId = selectedRunId ?? runs?.[0]?.run_id ?? null

  const { data: run, isLoading: runLoading } = useSmartMoneyRun(activeRunId)
  const { data: candidates, isLoading: candLoading } = useCandidates(activeRunId)
  const { data: disqualified } = useDisqualified(activeRunId)
  const { data: config, isLoading: cfgLoading } = useSmartMoneyConfig()
  const { data: gitStatus } = useConfigGitStatus()
  const { mutate: saveConfig, isPending: saving, error: saveErr } = useSaveConfig()
  const { mutate: runPipeline, isPending: launching } = useRunPipeline()
  const { mutate: stopPipeline, isPending: stopping } = useStopPipeline()

  const handleRunPipeline = () => {
    setIsStarting(true)
    runPipeline(profile, { onError: () => setIsStarting(false) })
  }

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
        <div className="ml-auto flex items-center gap-2">
          {/* Run selector — always shows the last COMPLETED run */}
          <div className="flex flex-col items-end gap-[3px]">
            {isLive && (
              <span className="flex items-center gap-[5px] text-[10px] font-mono text-accent leading-none">
                <span className="relative flex h-[6px] w-[6px]">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-60" />
                  <span className="relative inline-flex rounded-full h-[6px] w-[6px] bg-accent" />
                </span>
                new run in progress
              </span>
            )}
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
          </div>
          <button className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small border border-border-default bg-bg-surface text-text-primary hover:bg-bg-hover transition-colors duration-[120ms]">
            <Download size={14} />
            Export
          </button>
          {isLive ? (
            <button
              onClick={() => stopPipeline()}
              disabled={stopping || isStarting}
              className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small font-medium bg-neg border border-neg text-white hover:opacity-90 transition-opacity duration-[120ms] disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <span className="w-[8px] h-[8px] rounded-sm bg-white flex-shrink-0" />
              {stopping ? 'Stopping…' : isStarting ? 'Starting…' : 'Stop pipeline'}
            </button>
          ) : (
            <div className="flex items-center gap-[6px]">
              {/* Profile toggle: BOT / HUMAN */}
              <div className="flex rounded-md overflow-hidden border border-border-default text-[11px] font-mono">
                {(['bot', 'human'] as const).map(p => (
                  <button
                    key={p}
                    onClick={() => setProfile(p)}
                    className={`px-[10px] py-[5px] uppercase tracking-wide transition-colors duration-[120ms] ${
                      profile === p
                        ? 'bg-accent text-[#06201d] font-semibold'
                        : 'text-text-tertiary hover:text-text-primary bg-transparent'
                    }`}
                  >
                    {p}
                  </button>
                ))}
              </div>
              <button
                onClick={handleRunPipeline}
                disabled={launching}
                className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small font-medium bg-accent border border-accent text-[#06201d] hover:bg-accent-hover transition-colors duration-[120ms] disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Play size={14} />
                {launching ? 'Starting…' : 'Run pipeline'}
              </button>
            </div>
          )}
        </div>
      </div>

      {showProgress && effectiveProgress && <ScannerTerminal progress={effectiveProgress} />}

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
