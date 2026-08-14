import { useState, useRef, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Play, Download, Trash2 } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useSmartMoneyRuns,
  useSmartMoneyRun,
  useCandidates,
  useDisqualified,
  useSmartMoneyConfig,
  useConfigGitStatus,
  useSaveConfig,
  useRunProgress,
  useRunPipeline,
  useStopPipeline,
  useCacheStats,
  useClearCache,
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
  const isDone = progress.status === 'complete'
  const isError = progress.status === 'error'
  const isIdle = progress.status === 'idle'

  // During the scan phase, show per-scan progress (wallets_scanned / wallets_total)
  // instead of overall pipeline %. The backend pct is designed for a multi-stage
  // pipeline (scan = first 10%), which is misleading when only Stage 1 runs.
  const isScanPhase = isRunning && progress.wallets_total > 0
  const displayPct = isScanPhase
    ? Math.round((progress.wallets_scanned / progress.wallets_total) * 100)
    : isDone
      ? 100
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
  const seenRef = useRef(new Set<string>())
  const drainQueue = useRef<ScanEntry[]>([])
  const drainingRef = useRef(false)
  const feedIdRef = useRef(0)

  useEffect(() => {
    const incoming = progress.recent_addresses ?? []
    const newOnes = incoming.filter((e) => !seenRef.current.has(e.a))
    if (!newOnes.length) return

    drainQueue.current.push(...newOnes)
    if (drainingRef.current) return // already draining — let it continue

    drainingRef.current = true
    const step = () => {
      const entry = drainQueue.current.shift()
      if (!entry) {
        drainingRef.current = false
        return
      }
      seenRef.current.add(entry.a)
      setFeed((prev) => [{ ...entry, id: feedIdRef.current++ }, ...prev.slice(0, 17)])
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
  const scanRate = liveElapsed > 1 ? progress.wallets_scanned / liveElapsed : 0
  const isScan = isRunning && (progress.phase === 'scanning wallets' || feed.length > 0)
  // Only show stats bar when there is actual numeric content to display
  const showStats =
    progress.wallets_total > 0 ||
    progress.qualified_so_far > 0 ||
    progress.disqualified_so_far > 0 ||
    (isRunning && scanRate >= 0.5)

  // Border / bg colour based on state
  const wrapClass = isError
    ? 'border-neg bg-neg-muted'
    : isDone
      ? 'border-accent/40 bg-accent-muted'
      : isIdle
        ? 'border-border-subtle bg-bg-sunken'
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
          {isDone && <span className="w-[8px] h-[8px] rounded-full bg-accent flex-shrink-0" />}
          {isError && <span className="w-[8px] h-[8px] rounded-full bg-neg flex-shrink-0" />}
          {isIdle && (
            <span className="w-[8px] h-[8px] rounded-full bg-text-tertiary/30 flex-shrink-0" />
          )}
          <span
            className={`text-small font-semibold font-mono tracking-wide uppercase ${isIdle ? 'text-text-tertiary/50' : ''}`}
          >
            {isIdle ? 'Scanner' : progress.stage_name || `Stage ${progress.stage}`}
          </span>
          {progress.phase && !['complete', 'error', 'starting'].includes(progress.phase) && (
            <span className="text-micro text-text-tertiary font-mono">· {progress.phase}</span>
          )}
          {isDone && <span className="text-micro text-accent font-mono">· run complete</span>}
          {isIdle && <span className="text-micro text-text-tertiary/40 font-mono">· idle</span>}
        </div>
        {!isIdle && (
          <div className="flex items-center gap-4 font-mono text-micro">
            <span className="text-text-tertiary tabular-nums">{formatElapsed(liveElapsed)}</span>
            <span
              className={`font-semibold tabular-nums ${
                isDone
                  ? 'text-accent drop-shadow-glow-accent'
                  : isError
                    ? 'text-neg drop-shadow-glow-neg'
                    : 'text-accent drop-shadow-glow-accent'
              }`}
            >
              {displayPct}%
            </span>
          </div>
        )}
      </div>

      {/* ── Feed body ───────────────────────────────────────────────────── */}
      <div
        className={`relative overflow-hidden font-mono transition-[height] duration-500 ease-in-out ${isRunning ? 'h-[176px] py-3 px-4' : isIdle ? 'h-[80px]' : 'h-[40px] py-3 px-4'}`}
      >
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
                    <span className="text-accent font-semibold tracking-widest text-[10px] drop-shadow-glow-accent">
                      PASS ✓
                    </span>
                  ) : (
                    <span className="text-neg font-semibold tracking-widest text-[10px]">
                      FAIL ✗
                    </span>
                  )}
                </div>
              )
            })}
          </div>
        ) : isIdle ? (
          /* ── Coma heartbeat — continuous scrolling waveform ─────────── */
          // Soft left/right mask makes the line feel infinite in both directions
          <div
            className="relative w-full h-full"
            style={{
              maskImage:
                'linear-gradient(to right, transparent 0%, black 6%, black 94%, transparent 100%)',
              WebkitMaskImage:
                'linear-gradient(to right, transparent 0%, black 6%, black 94%, transparent 100%)',
            }}
          >
            {/*
              1000px SVG = 5 × 200px identical repeats.
              ecgScroll slides it -200px then loops — completely seamless because
              each repeat is identical, so the snap back is invisible.
              Peak: y=10, only 6px above y=16 baseline — subtle coma-level amplitude.
            */}
            <svg
              width="2000"
              height="32"
              viewBox="0 0 2000 32"
              className="absolute animate-ecg-scroll pointer-events-none"
              style={{ top: 'calc(50% - 16px)', left: 0 }}
            >
              <path
                d="M0,16 L85,16 C90,16 92,10 100,10 C108,10 110,16 115,16 L200,16 L285,16 C290,16 292,10 300,10 C308,10 310,16 315,16 L400,16 L485,16 C490,16 492,10 500,10 C508,10 510,16 515,16 L600,16 L685,16 C690,16 692,10 700,10 C708,10 710,16 715,16 L800,16 L885,16 C890,16 892,10 900,10 C908,10 910,16 915,16 L1000,16 L1085,16 C1090,16 1092,10 1100,10 C1108,10 1110,16 1115,16 L1200,16 L1285,16 C1290,16 1292,10 1300,10 C1308,10 1310,16 1315,16 L1400,16 L1485,16 C1490,16 1492,10 1500,10 C1508,10 1510,16 1515,16 L1600,16 L1685,16 C1690,16 1692,10 1700,10 C1708,10 1710,16 1715,16 L1800,16 L1885,16 C1890,16 1892,10 1900,10 C1908,10 1910,16 1915,16 L2000,16"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                className="text-accent/60"
              />
            </svg>
          </div>
        ) : (
          /* ── Status view for active phases ─────────────────────────── */
          <div className="flex flex-col justify-center h-full gap-[8px]">
            <div className="flex items-center gap-[10px] text-[12px] font-mono">
              {isRunning && <span className="text-accent text-[10px]">▶</span>}
              {isDone && <span className="text-accent">✓</span>}
              {isError && <span className="text-neg">✗</span>}
              <span
                className={
                  isError ? 'text-neg-text' : isDone ? 'text-accent-text' : 'text-text-secondary'
                }
              >
                {isError
                  ? progress.message || 'Error'
                  : isDone
                    ? progress.wallets_scanned > 0
                      ? `${progress.wallets_scanned.toLocaleString()} wallets processed`
                      : 'Completed'
                    : progress.message || progress.phase || 'Starting…'}
              </span>
              {isRunning && <span className="text-accent animate-pulse leading-none">█</span>}
            </div>
            {/* Show phase progress for profiling/scoring steps */}
            {isRunning && progress.wallets_total > 0 && !isScan && (
              <div className="text-[10px] text-text-tertiary font-mono tabular-nums">
                {progress.wallets_scanned.toLocaleString()} /{' '}
                {progress.wallets_total.toLocaleString()} wallets processed
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Stats bar ───────────────────────────────────────────────────── */}
      {showStats && (
        <div className="px-4 py-[7px] border-t border-border-subtle flex items-center gap-5 font-mono text-[11px] flex-wrap">
          {/* Wallet count only shown while running — body text already shows it when done */}
          {!isDone && progress.wallets_total > 0 && (
            <span className="text-text-tertiary tabular-nums">
              <span className="text-text-secondary font-medium">
                {progress.wallets_scanned.toLocaleString()}
              </span>
              {' / '}
              {progress.wallets_total.toLocaleString()} wallets
            </span>
          )}
          {isRunning && scanRate >= 0.5 && (
            <span className="text-text-tertiary tabular-nums">
              <span className="text-text-secondary">{scanRate.toFixed(1)}</span> wallets/sec
            </span>
          )}
          {progress.qualified_so_far > 0 && (
            <span className="text-accent tabular-nums drop-shadow-glow-accent">
              <span className="font-semibold">{progress.qualified_so_far}</span> qualified
            </span>
          )}
          {progress.disqualified_so_far > 0 && (
            <span className="text-text-tertiary tabular-nums">
              {progress.disqualified_so_far.toLocaleString()} eliminated
            </span>
          )}
        </div>
      )}

      {/* ── Progress bar (hidden when idle) ─────────────────────────────── */}
      {!isIdle && (
        <div className="h-[3px] bg-bg-surface-2">
          <div
            className={`h-full transition-[width] duration-700 ease-out ${
              isError ? 'bg-neg' : 'bg-accent'
            }`}
            style={{ width: `${Math.max(displayPct, isRunning ? 1 : 0)}%` }}
          />
        </div>
      )}
    </div>
  )
}

// ── RunPendingPlaceholder ─────────────────────────────────────────────────────

function RunPendingPlaceholder() {
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-4 text-center">
      <div className="flex items-center gap-2">
        <span className="relative flex h-[10px] w-[10px]">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-60" />
          <span className="relative inline-flex rounded-full h-[10px] w-[10px] bg-accent" />
        </span>
        <span className="text-accent font-mono text-[13px] font-semibold tracking-wide">
          RUN IN PROGRESS
        </span>
      </div>
      <p className="text-text-tertiary text-small max-w-xs">
        Results will populate here when the pipeline completes.
      </p>
    </div>
  )
}

// ── Main SmartMoney page ──────────────────────────────────────────────────────

type Tab = 'overview' | 'rankings' | 'profile' | 'disqualified' | 'config'

const TABS: Array<{ id: Tab; label: string }> = [
  { id: 'overview', label: 'Pool Overview' },
  { id: 'rankings', label: 'Rankings' },
  { id: 'profile', label: 'Candidate Profile' },
  { id: 'disqualified', label: 'Disqualified' },
  { id: 'config', label: 'Config' },
]

// Placeholder progress shown immediately after clicking "Run pipeline", before
// Python has had time to start and write a real progress.json (takes 10–15s).
const STARTING_PROGRESS: RunProgress = {
  run_id: '',
  status: 'running',
  stage: 1,
  stage_name: 'Hyperliquid scan',
  phase: 'starting',
  pct: 0,
  wallets_scanned: 0,
  wallets_total: 0,
  qualified_so_far: 0,
  disqualified_so_far: 0,
  message: 'Launching pipeline…',
  started_at: new Date().toISOString(),
  updated_at: null,
  elapsed_seconds: 0,
  recent_addresses: [],
}

export function SmartMoney() {
  const qc = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const [selectedCandidate, setSelectedCandidate] = useState<Candidate | null>(null)
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)

  // 'profile' requires selectedCandidate — fall back to rankings if arriving cold
  const rawTab = (searchParams.get('tab') ?? 'overview') as Tab
  const tab = rawTab === 'profile' && !selectedCandidate ? 'rankings' : rawTab
  const setTab = (t: Tab) => setSearchParams({ tab: t }, { replace: true })
  const [rankingsMarket, setRankingsMarket] = useState<'all' | 'crypto' | 'forex'>('all')

  // isStarting: true from the moment "Run pipeline" is clicked until the backend
  // confirms the run is actually running. Prevents the terminal from flickering
  // back to "complete" while Python is starting up (10–15s).
  const [isStarting, setIsStarting] = useState(false)
  // profile: which config template to use when triggering a run
  const [profile, setProfile] = useState<'bot' | 'human'>('bot')
  // confirmClear: two-step guard before deleting the fills cache
  const [confirmClear, setConfirmClear] = useState(false)

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
  const effectiveProgress =
    isStarting && progress?.status !== 'running' ? STARTING_PROGRESS : progress

  const isLive = isStarting || progress?.status === 'running'

  const { data: runs } = useSmartMoneyRuns()
  const activeRunId = selectedRunId ?? runs?.[0]?.run_id ?? null

  // Terminal is tied to progress.json (always the latest run). Hide it when
  // the user has explicitly selected a historical run — showing the latest
  // run's terminal while browsing older data is confusing.
  const isViewingHistoricalRun =
    selectedRunId !== null && runs != null && runs.length > 0 && selectedRunId !== runs[0].run_id
  const showProgress = effectiveProgress != null && !isViewingHistoricalRun

  const { data: run, isLoading: runLoading } = useSmartMoneyRun(activeRunId)
  const { data: candidates, isLoading: candLoading } = useCandidates(activeRunId)
  const { data: disqualified } = useDisqualified(activeRunId)
  const { data: config, isLoading: cfgLoading } = useSmartMoneyConfig()
  const { data: gitStatus } = useConfigGitStatus()
  const { mutate: saveConfig, isPending: saving, error: saveErr } = useSaveConfig()
  const { mutate: runPipeline, isPending: launching } = useRunPipeline()
  const { mutate: stopPipeline, isPending: stopping } = useStopPipeline()
  const { data: cacheStats } = useCacheStats()
  const { mutate: clearCache, isPending: clearing } = useClearCache()

  const handleRunPipeline = () => {
    setIsStarting(true)
    runPipeline(profile, { onError: () => setIsStarting(false) })
  }

  const handleSelectCandidate = (c: Candidate) => {
    setSelectedCandidate(c)
    setTab('profile')
  }

  const runDate = run?.generated_at
    ? new Date(run.generated_at).toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    : null

  return (
    <div>
      {/* Page header */}
      <div className="flex items-end gap-3 mb-[18px]">
        <h1 className="text-h1 font-semibold">Smart Money</h1>
        {!isLive && runDate && (
          <span className="text-[12px] text-text-tertiary pb-[2px]">{runDate}</span>
        )}
        <div className="ml-auto flex items-center gap-2">
          {isLive ? (
            /* ── Live: show status pill + stop only — no dropdown, no export ── */
            <>
              <span className="flex items-center gap-[7px] px-3 py-[6px] rounded-md border border-accent/30 bg-accent/5 text-accent font-mono text-[11px] font-semibold tracking-wide">
                <span className="relative flex h-[7px] w-[7px]">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-60" />
                  <span className="relative inline-flex rounded-full h-[7px] w-[7px] bg-accent" />
                </span>
                RUN IN PROGRESS
              </span>
              <button
                onClick={() => stopPipeline()}
                disabled={stopping || isStarting}
                className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small font-medium bg-neg border border-neg text-white hover:opacity-90 transition-opacity duration-[120ms] disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <span className="w-[8px] h-[8px] rounded-sm bg-white flex-shrink-0" />
                {stopping ? 'Stopping…' : isStarting ? 'Starting…' : 'Stop pipeline'}
              </button>
            </>
          ) : (
            /* ── Idle: show run selector, export, profile toggle + run button ── */
            <>
              {runs && runs.length > 0 && (
                <select
                  value={activeRunId ?? ''}
                  onChange={(e) => setSelectedRunId(e.target.value)}
                  className="bg-bg-surface border border-border-default rounded-md px-3 py-[6px] text-small text-text-primary focus:outline-none focus:border-accent"
                >
                  {runs.map((r) => (
                    <option key={r.run_id} value={r.run_id}>
                      {new Date(r.generated_at).toLocaleString('en-US', {
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}{' '}
                      · {r.total_qualified} qualified
                    </option>
                  ))}
                </select>
              )}
              <button
                disabled
                title="Export coming soon"
                className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small border border-border-default bg-bg-surface text-text-tertiary opacity-40 cursor-not-allowed"
              >
                <Download size={14} />
                Export
              </button>

              {/* ── Clear cache — two-step confirmation ── */}
              {!confirmClear ? (
                <button
                  onClick={() => setConfirmClear(true)}
                  disabled={!cacheStats || cacheStats.wallets_cached === 0}
                  title={
                    !cacheStats || cacheStats.wallets_cached === 0
                      ? 'Cache is empty'
                      : `${cacheStats.wallets_cached} wallets cached — click to clear before next scan`
                  }
                  className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small border border-border-default bg-bg-surface text-text-secondary hover:text-warn hover:border-warn/40 transition-colors duration-[120ms] disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:text-text-secondary disabled:hover:border-border-default"
                >
                  <Trash2 size={13} />
                  {cacheStats && cacheStats.wallets_cached > 0
                    ? `Clear cache (${cacheStats.wallets_cached})`
                    : 'Clear cache'}
                </button>
              ) : (
                <div className="flex items-center gap-[8px] px-3 py-[5px] rounded-md border border-warn/40 bg-warn/5 text-[11px] font-mono whitespace-nowrap">
                  <span className="text-warn">⚠</span>
                  <span className="text-text-secondary">
                    Clear {cacheStats?.wallets_cached} cached wallets?
                  </span>
                  <button
                    onClick={() => setConfirmClear(false)}
                    className="text-text-tertiary hover:text-text-primary transition-colors duration-[120ms] ml-1"
                  >
                    Cancel
                  </button>
                  <span className="text-border-subtle">·</span>
                  <button
                    onClick={() => {
                      clearCache()
                      setConfirmClear(false)
                    }}
                    disabled={clearing}
                    className="text-warn font-semibold hover:text-warn/80 transition-colors duration-[120ms] disabled:opacity-50"
                  >
                    {clearing ? 'Clearing…' : 'Yes, clear'}
                  </button>
                </div>
              )}

              <div className="flex items-center gap-[6px]">
                {/* Profile toggle: BOT / HUMAN */}
                <div className="flex rounded-md overflow-hidden border border-border-default text-[11px] font-mono">
                  {(['bot', 'human'] as const).map((p) => (
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
            </>
          )}
        </div>
      </div>

      {showProgress && effectiveProgress && <ScannerTerminal progress={effectiveProgress} />}

      {/* Tabs — entirely non-interactive while a run is live */}
      <div
        className={`flex gap-[2px] mb-[18px] border-b border-border-subtle ${isLive ? 'pointer-events-none' : ''}`}
      >
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`text-small px-[13px] py-2 border-b-2 -mb-px transition-colors duration-[120ms] ${
              isLive
                ? 'text-text-tertiary/40 border-transparent cursor-default'
                : tab === t.id
                  ? 'text-text-primary border-accent cursor-pointer'
                  : 'text-text-secondary border-transparent hover:text-text-primary cursor-pointer'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content — all tabs locked while a run is live */}
      {isLive ? (
        <RunPendingPlaceholder />
      ) : (
        <>
          {tab === 'overview' &&
            (runLoading ? (
              <div className="text-text-tertiary text-small py-12 text-center">Loading…</div>
            ) : run ? (
              <PoolOverview
                run={run}
                onNavigate={(t, m) => {
                  if (m) setRankingsMarket(m as 'all' | 'crypto' | 'forex')
                  setTab(t as Tab)
                }}
              />
            ) : (
              <PoolOverviewEmpty />
            ))}

          {tab === 'rankings' &&
            (candLoading ? (
              <div className="text-text-tertiary text-small py-12 text-center">
                Loading candidates…
              </div>
            ) : candidates && candidates.length > 0 ? (
              <Rankings
                candidates={candidates}
                onSelect={handleSelectCandidate}
                initialMarket={rankingsMarket}
              />
            ) : (
              <div className="text-center py-12 text-text-tertiary text-small">
                No candidates found in this run.
              </div>
            ))}

          {tab === 'profile' &&
            (selectedCandidate ? (
              <CandidateProfile candidate={selectedCandidate} onBack={() => setTab('rankings')} />
            ) : (
              <div className="text-center py-12 text-text-tertiary text-small">
                Select a candidate from the Rankings tab to view their full profile.
              </div>
            ))}

          {tab === 'disqualified' &&
            (disqualified ? (
              <DisqualifiedLog disqualified={disqualified} />
            ) : (
              <div className="text-center py-12 text-text-tertiary text-small">
                No disqualified log available for this run.
              </div>
            ))}

          {tab === 'config' &&
            (cfgLoading ? (
              <div className="text-text-tertiary text-small py-12 text-center">Loading config…</div>
            ) : config ? (
              <Config
                config={config}
                gitStatus={gitStatus}
                onSave={saveConfig}
                isSaving={saving}
                saveError={saveErr ? String(saveErr) : null}
              />
            ) : (
              <div className="text-center py-12 text-neg-text text-small">
                Could not load pipeline config. Check that the config file path in Settings is
                correct.
              </div>
            ))}
        </>
      )}
    </div>
  )
}
