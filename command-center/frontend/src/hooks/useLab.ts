import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api } from '@/api/client'
import type {
  Strategy, ScanResult, DeployJobStatus,
  Ruleset, RulesetCreate,
  BacktestRunRequest, BacktestSummary, BacktestDetail,
  LabProgress, SystemHealth,
  SweepRequest, SweepResponse, SweepDetail,
  OptimizationRequest, OptimizationSummary, OptimizationDetail,
  InstrumentSummary, RunningJobStatus,
  BackfillRegimeStatus,
  StrategyFile, StrategyFileSyncStatus, CompileJobStatus,
} from '@/types'

// ── Strategies ─────────────────────────────────────────────────────────────────

export function useStrategies() {
  return useQuery({
    queryKey: ['lab', 'strategies'],
    queryFn: () => api.get<Strategy[]>('/strategies'),
  })
}

export function useStrategy(strategyId: string | null) {
  return useQuery({
    queryKey: ['lab', 'strategies', strategyId],
    queryFn: () => api.get<Strategy>(`/strategies/${strategyId}`),
    enabled: !!strategyId,
  })
}

export function useParamTypes(strategyId: string | null) {
  return useQuery({
    queryKey: ['lab', 'strategies', strategyId, 'param-types'],
    queryFn: () => api.get<Record<string, 'int' | 'double'>>(`/strategies/${strategyId}/param-types`),
    enabled: !!strategyId,
    staleTime: Infinity,
  })
}

export function useUpdateStrategyDescription() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ strategyId, description }: { strategyId: string; description: string }) =>
      api.patch<Strategy>(`/strategies/${strategyId}`, { description }),
    onSuccess: (data) => {
      qc.setQueryData(['lab', 'strategies', data.id], data)
      qc.invalidateQueries({ queryKey: ['lab', 'strategies'] })
    },
    onError: () => toast.error('Failed to save description'),
  })
}

export function useDeployStrategy() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (strategyId: string) => {
      const { deploy_job_id } = await api.post<{ deploy_job_id: string }>(`/strategies/${strategyId}/deploy`, {})
      return api.get<DeployJobStatus>(`/strategies/${strategyId}/deploy/${deploy_job_id}`)
    },
    onSuccess: (data) => {
      toast.success(`${data.filename} deployed`)
      qc.invalidateQueries({ queryKey: ['lab', 'strategy-files', 'sync-status'] })
      qc.invalidateQueries({ queryKey: ['lab', 'strategy-files'] })
    },
    onError: (err: Error) => toast.error(`Deploy failed: ${err.message}`),
  })
}

export function useScanStrategies() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<ScanResult>('/strategies/scan'),
    onSuccess: (data) => {
      toast.success(`Scanned — ${data.added} added, ${data.updated} updated`)
      qc.invalidateQueries({ queryKey: ['lab', 'strategies'] })
    },
    onError: () => toast.error('Strategy scan failed'),
  })
}

// ── Rulesets ───────────────────────────────────────────────────────────────────

export function useRulesets() {
  return useQuery({
    queryKey: ['lab', 'rulesets'],
    queryFn: () => api.get<Ruleset[]>('/rulesets'),
  })
}

// Backward-compat alias — components not yet updated use this
export const useFirms = useRulesets

export function useCreateRuleset() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: RulesetCreate) => api.post<Ruleset>('/rulesets', body),
    onSuccess: () => {
      toast.success('Ruleset created')
      qc.invalidateQueries({ queryKey: ['lab', 'rulesets'] })
    },
    onError: () => toast.error('Failed to create ruleset'),
  })
}

export function useUpdateRuleset() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ rulesetId, body }: { rulesetId: string; body: RulesetCreate }) =>
      api.put<Ruleset>(`/rulesets/${rulesetId}`, body),
    onSuccess: () => {
      toast.success('Ruleset updated')
      qc.invalidateQueries({ queryKey: ['lab', 'rulesets'] })
    },
    onError: () => toast.error('Failed to update ruleset'),
  })
}

export function useDeleteRuleset() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (rulesetId: string) => api.delete<void>(`/rulesets/${rulesetId}`),
    onSuccess: () => {
      toast.success('Ruleset deleted')
      qc.invalidateQueries({ queryKey: ['lab', 'rulesets'] })
    },
    onError: () => toast.error('Failed to delete ruleset'),
  })
}

// ── Backtest Runs ──────────────────────────────────────────────────────────────

export function useBacktestRuns(filters?: {
  strategy_id?: string
  ruleset_id?: string
  status?: string
}) {
  const params = new URLSearchParams()
  if (filters?.strategy_id) params.set('strategy_id', filters.strategy_id)
  if (filters?.ruleset_id)  params.set('ruleset_id',  filters.ruleset_id)
  if (filters?.status)      params.set('status',      filters.status)
  const qs = params.toString()

  return useQuery({
    queryKey: ['lab', 'runs', filters ?? {}],
    queryFn: () => api.get<BacktestSummary[]>(`/backtests/runs${qs ? `?${qs}` : ''}`),
  })
}

export function useBacktestRun(runId: string | null) {
  return useQuery({
    queryKey: ['lab', 'run', runId],
    queryFn: () => api.get<BacktestDetail>(`/backtests/runs/${runId}`),
    enabled: !!runId,
    refetchInterval: (query) => {
      const status = (query.state.data as BacktestDetail | undefined)?.status
      return status === 'running' ? 1_500 : false
    },
  })
}

export function useRunLog(runId: string | null, lines = 200, live = false) {
  return useQuery({
    queryKey: ['lab', 'run', runId, 'log', lines],
    queryFn: () => api.getText(`/backtests/runs/${runId}/log?lines=${lines}`),
    enabled: !!runId,
    refetchInterval: live ? 2_000 : false,
  })
}

export function useOptimizationLog(optimizationId: string | null, lines = 300, live = false) {
  return useQuery({
    queryKey: ['lab', 'optimization', optimizationId, 'log', lines],
    queryFn: () => api.getText(`/optimizations/${optimizationId}/log?lines=${lines}`),
    enabled: !!optimizationId,
    refetchInterval: live ? 2_000 : false,
  })
}

// Module-level timestamp: keeps progress polling fast for 60s after a trigger
// so the UI reflects state changes while the NT8 agent starts the job.
let _lastTriggerMs = 0

export function useTriggerBacktest() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: BacktestRunRequest) =>
      api.post<{ run_id: string; status: string }>('/backtests/run', body),
    onSuccess: () => {
      _lastTriggerMs = Date.now()
      toast.success('Backtest started')
      qc.invalidateQueries({ queryKey: ['lab', 'runs'] })
      qc.invalidateQueries({ queryKey: ['lab', 'progress'] })
      qc.invalidateQueries({ queryKey: ['lab', 'running-job'] })
    },
    onError: (e: unknown) => {
      const detail = (e as { detail?: string })?.detail
      if (detail?.includes('already running')) {
        toast.error(detail)
      } else {
        toast.error('Failed to start backtest')
      }
    },
  })
}

export function useDeleteRun() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (runId: string) => api.delete<void>(`/backtests/runs/${runId}`),
    onSuccess: () => {
      toast.success('Run deleted')
      qc.invalidateQueries({ queryKey: ['lab', 'runs'] })
    },
    onError: () => toast.error('Failed to delete run'),
  })
}

export function useDeleteOptimization() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (optId: string) => api.delete<void>(`/optimizations/${optId}`),
    onSuccess: () => {
      toast.success('Optimization deleted')
      qc.invalidateQueries({ queryKey: ['lab', 'optimizations'] })
      qc.invalidateQueries({ queryKey: ['lab', 'runs'] })
    },
    onError: (e: unknown) => {
      const msg = (e as { detail?: string })?.detail
      toast.error(msg ?? 'Failed to delete optimization')
    },
  })
}

export function useStopBacktest() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (runId: string) =>
      api.post<{ run_id: string; status: string }>(`/backtests/runs/${runId}/stop`),
    onSuccess: (_data, runId) => {
      toast.success('Backtest cancelled')
      qc.invalidateQueries({ queryKey: ['lab', 'run', runId] })
      qc.invalidateQueries({ queryKey: ['lab', 'runs'] })
      qc.invalidateQueries({ queryKey: ['lab', 'running-job'] })
    },
    onError: () => toast.error('Failed to stop backtest'),
  })
}

export function useRetryBacktest() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (runId: string) =>
      api.post<{ run_id: string; status: string }>(`/backtests/runs/${runId}/retry`),
    onSuccess: (data) => {
      toast.success('Rerun started')
      qc.invalidateQueries({ queryKey: ['lab', 'runs'] })
      qc.invalidateQueries({ queryKey: ['lab', 'run', data.run_id] })
      qc.invalidateQueries({ queryKey: ['lab', 'sweep'] })
      qc.invalidateQueries({ queryKey: ['lab', 'sweeps'] })
      qc.invalidateQueries({ queryKey: ['lab', 'optimization'] })
      qc.invalidateQueries({ queryKey: ['lab', 'optimizations'] })
      qc.invalidateQueries({ queryKey: ['lab', 'running-job'] })
    },
    onError: (e: unknown) => {
      const msg = (e as { detail?: string })?.detail
      toast.error(msg ?? 'Failed to start rerun')
    },
  })
}

export function useReevaluate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ runId, firmIds }: { runId: string; firmIds: string[] }) =>
      api.post<BacktestDetail>(`/backtests/runs/${runId}/reevaluate`, { firm_ids: firmIds }),
    onSuccess: (_data, vars) => {
      toast.success('Re-evaluated')
      qc.invalidateQueries({ queryKey: ['lab', 'run', vars.runId] })
    },
    onError: () => toast.error('Re-evaluate failed'),
  })
}

export function useReloadCharts() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (runId: string) =>
      api.post<{ equity_points: number; daily_bars: number }>(`/backtests/runs/${runId}/reload-charts`),
    onSuccess: (data, runId) => {
      toast.success(`Charts loaded — ${data.equity_points} trades, ${data.daily_bars} trading days`)
      qc.invalidateQueries({ queryKey: ['lab', 'run', runId] })
    },
    onError: () => toast.error('Chart reload failed — check NT8 agent and SA'),
  })
}

// ── Lab Progress + Control ─────────────────────────────────────────────────────

export function useLabProgress() {
  return useQuery({
    queryKey: ['lab', 'progress'],
    queryFn: () => api.get<LabProgress>('/lab/progress'),
    refetchInterval: (query) => {
      const status = (query.state.data as LabProgress | undefined)?.status
      if (Date.now() - _lastTriggerMs < 60_000) return 2_000
      return status === 'running' ? 1_500 : 30_000
    },
  })
}

export function useStopLab() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () =>
      api.post<{ stopped: boolean; job_id: string | null }>('/lab/stop', {}),
    onSuccess: (data) => {
      if (data.stopped) toast.success('Lab job cancelled')
      else toast.error('No active job to stop')
      qc.invalidateQueries({ queryKey: ['lab', 'progress'] })
      qc.invalidateQueries({ queryKey: ['lab', 'running-job'] })
    },
    onError: () => toast.error('Failed to stop lab'),
  })
}

// ── System Health ──────────────────────────────────────────────────────────────

export function useSystemHealth() {
  return useQuery({
    queryKey: ['system', 'health'],
    queryFn: () => api.get<SystemHealth>('/system/health'),
    refetchInterval: 30_000,
  })
}

export function useStartNt8Agent() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<{ status: string; output: string }>('/system/nt8-agent/start'),
    onSuccess: () => {
      toast.success('NT8 agent starting…')
      setTimeout(() => qc.invalidateQueries({ queryKey: ['system', 'health'] }), 8_000)
    },
    onError: () => toast.error('Failed to start NT8 agent — is SSH up?'),
  })
}

export function useStartMt5Agent() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<{ status: string; output: string }>('/system/mt5-agent/start'),
    onSuccess: () => {
      toast.success('MT5 agent starting…')
      setTimeout(() => qc.invalidateQueries({ queryKey: ['system', 'health'] }), 8_000)
    },
    onError: () => toast.error('Failed to start MT5 agent — is SSH up?'),
  })
}

// ── Sweeps ─────────────────────────────────────────────────────────────────────

export function useSweeps(strategyId?: string) {
  const qs = strategyId ? `?strategy_id=${strategyId}` : ''
  return useQuery({
    queryKey: ['lab', 'sweeps', strategyId ?? ''],
    queryFn: () => api.get<import('@/types').SweepSummary[]>(`/backtests/sweeps${qs}`),
    refetchInterval: 30_000,
  })
}

export function useSweep(sweepId: string | null) {
  return useQuery({
    queryKey: ['lab', 'sweep', sweepId],
    queryFn: () => api.get<SweepDetail>(`/backtests/sweeps/${sweepId}`),
    enabled: !!sweepId,
    refetchInterval: (query) => {
      const data = query.state.data as SweepDetail | undefined
      if (!data) return 5_000
      return data.completed_instruments < data.total_instruments ? 3_000 : false
    },
  })
}

export function useDeleteSweep() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (sweepId: string) => api.delete<void>(`/backtests/sweeps/${sweepId}`),
    onSuccess: () => {
      toast.success('Sweep deleted')
      qc.invalidateQueries({ queryKey: ['lab', 'sweeps'] })
      qc.invalidateQueries({ queryKey: ['lab', 'runs'] })
    },
    onError: (e: unknown) => {
      const msg = (e as { detail?: string })?.detail
      toast.error(msg ?? 'Failed to delete sweep')
    },
  })
}

export function useCancelSweep() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (sweepId: string) =>
      api.post<{ sweep_id: string; status: string }>(`/backtests/sweeps/${sweepId}/cancel`),
    onSuccess: (_data, sweepId) => {
      toast.success('Sweep cancelled')
      qc.invalidateQueries({ queryKey: ['lab', 'sweep', sweepId] })
      qc.invalidateQueries({ queryKey: ['lab', 'sweeps'] })
    },
    onError: (e: unknown) => {
      const msg = (e as { detail?: string })?.detail
      toast.error(msg ?? 'Failed to cancel sweep')
    },
  })
}

export function useRetrySweep() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (sweepId: string) =>
      api.post<{ sweep_id: string; retrying: number; status: string }>(`/backtests/sweeps/${sweepId}/retry-failed`),
    onSuccess: (data, sweepId) => {
      toast.success(`Retrying ${data.retrying} failed run${data.retrying !== 1 ? 's' : ''}`)
      qc.invalidateQueries({ queryKey: ['lab', 'sweep', sweepId] })
      qc.invalidateQueries({ queryKey: ['lab', 'sweeps'] })
    },
    onError: (e: unknown) => {
      const msg = (e as { detail?: string })?.detail
      toast.error(msg ?? 'Failed to retry sweep')
    },
  })
}

export function useReevaluateSweep() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ sweepId, ruleset_ids }: { sweepId: string; ruleset_ids: string[] }) =>
      api.post<{ sweep_id: string; reevaluated: number }>(`/backtests/sweeps/${sweepId}/reevaluate`, { ruleset_ids }),
    onSuccess: (data, { sweepId }) => {
      toast.success(`Scored ${data.reevaluated} run${data.reevaluated !== 1 ? 's' : ''}`)
      qc.invalidateQueries({ queryKey: ['lab', 'sweep', sweepId] })
      qc.invalidateQueries({ queryKey: ['lab', 'sweeps'] })
    },
    onError: (e: unknown) => {
      const msg = (e as { detail?: string })?.detail
      toast.error(msg ?? 'Re-evaluation failed')
    },
  })
}

export function useTriggerSweep() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: SweepRequest) => api.post<SweepResponse>('/backtests/sweep', body),
    onSuccess: () => {
      toast.success('Sweep started')
      qc.invalidateQueries({ queryKey: ['lab', 'runs'] })
      qc.invalidateQueries({ queryKey: ['lab', 'sweeps'] })
      qc.invalidateQueries({ queryKey: ['lab', 'running-job'] })
    },
    onError: (e: unknown) => {
      const detail = (e as { detail?: string })?.detail
      if (detail?.includes('already running')) {
        toast.error(detail)
      } else {
        toast.error('Failed to start sweep')
      }
    },
  })
}

// ── Optimizations ──────────────────────────────────────────────────────────────

export function useOptimizations(strategyId?: string) {
  const qs = strategyId ? `?strategy_id=${strategyId}` : ''
  return useQuery({
    queryKey: ['lab', 'optimizations', strategyId ?? 'all'],
    queryFn: () => api.get<OptimizationSummary[]>(`/optimizations${qs}`),
    refetchInterval: (query) => {
      const data = query.state.data as OptimizationSummary[] | undefined
      return data?.some(o => o.status === 'running') ? 3_000 : 15_000
    },
  })
}

export function useOptimization(optimizationId: string | null) {
  return useQuery({
    queryKey: ['lab', 'optimization', optimizationId],
    queryFn: () => api.get<OptimizationDetail>(`/optimizations/${optimizationId}`),
    enabled: !!optimizationId,
    refetchInterval: (query) => {
      const data = query.state.data as OptimizationDetail | undefined
      if (!data) return false
      const hasRunning = data.runs.some(r => r.status === 'running')
      return (data.status === 'running' || hasRunning) ? 3_000 : false
    },
  })
}

export function useTriggerOptimization() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: OptimizationRequest) =>
      api.post<{ optimization_id: string; status: string; estimated_runs: number }>('/optimizations/run', body),
    onSuccess: () => {
      toast.success('Optimization started')
      qc.invalidateQueries({ queryKey: ['lab', 'optimizations'] })
      qc.invalidateQueries({ queryKey: ['lab', 'running-job'] })
    },
    onError: (e: unknown) => {
      const detail = (e as { detail?: string })?.detail
      if (detail?.includes('already running')) {
        toast.error(detail)
      } else {
        toast.error('Failed to start optimization')
      }
    },
  })
}

export function useCancelOptimization() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (optimizationId: string) =>
      api.post<{ optimization_id: string; status: string }>(`/optimizations/${optimizationId}/cancel`),
    onSuccess: (_data, optimizationId) => {
      toast.success('Optimization cancelled')
      qc.invalidateQueries({ queryKey: ['lab', 'optimization', optimizationId] })
      qc.invalidateQueries({ queryKey: ['lab', 'optimizations'] })
    },
    onError: () => toast.error('Failed to cancel optimization'),
  })
}

export function useRetryOptimization() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (optimizationId: string) =>
      api.post<{ optimization_id: string; retrying: number; status: string }>(`/optimizations/${optimizationId}/retry-failed`),
    onSuccess: (data, optimizationId) => {
      toast.success(`Retrying ${data.retrying} failed run${data.retrying !== 1 ? 's' : ''}`)
      qc.invalidateQueries({ queryKey: ['lab', 'optimization', optimizationId] })
      qc.invalidateQueries({ queryKey: ['lab', 'optimizations'] })
    },
    onError: () => toast.error('Failed to retry optimization'),
  })
}

export function useRerunOptimization() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (optimizationId: string) =>
      api.post<{ optimization_id: string; status: string; estimated_runs: number }>(`/optimizations/${optimizationId}/rerun`),
    onSuccess: (_data, optimizationId) => {
      qc.invalidateQueries({ queryKey: ['lab', 'optimization', optimizationId] })
      qc.invalidateQueries({ queryKey: ['lab', 'optimizations'] })
    },
    onError: () => toast.error('Failed to re-run optimization'),
  })
}

// ── Instrument Summary ─────────────────────────────────────────────────────────

export function useInstrumentSummary(
  strategyId: string | null,
  rulesetId?: string,
  startDate?: string,
  endDate?: string,
) {
  const params = new URLSearchParams()
  if (rulesetId) params.set('ruleset_id', rulesetId)
  if (startDate) params.set('start_date', startDate)
  if (endDate)   params.set('end_date',   endDate)
  const qs = params.toString()

  return useQuery({
    queryKey: ['lab', 'instrument-summary', strategyId, rulesetId, startDate, endDate],
    queryFn: () => api.get<InstrumentSummary>(`/strategies/${strategyId}/instrument_summary${qs ? `?${qs}` : ''}`),
    enabled: !!strategyId,
  })
}

// ── Running VPS job ───────────────────────────────────────────────────────────

export function useRunningVpsJob() {
  return useQuery({
    queryKey: ['lab', 'running-job'],
    queryFn: () => api.get<RunningJobStatus>('/backtests/running-job'),
    refetchInterval: 5_000,
  })
}

// ── Regime Backfill ────────────────────────────────────────────────────────────

export function useBackfillRegime() {
  return useMutation({
    mutationFn: (runId: string) =>
      api.post<{ run_id: string; status: string }>(`/backtests/runs/${runId}/backfill_regime`),
    onError: () => toast.error('Failed to start regime backfill'),
  })
}

export function useBackfillStatus(runId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ['lab', 'backfill-status', runId],
    queryFn: () => api.get<BackfillRegimeStatus>(`/backtests/runs/${runId}/backfill_status`),
    enabled: !!runId && enabled,
    refetchInterval: (query) => {
      const data = query.state.data as BackfillRegimeStatus | undefined
      return data?.status === 'running' ? 1_000 : false
    },
  })
}

// ── VPS Log Proxies ────────────────────────────────────────────────────────────

export function useVpsAgentLog(lines = 200) {
  return useQuery({
    queryKey: ['lab', 'vps', 'agent-log', lines],
    queryFn: () => api.getText(`/vps/agent/log?lines=${lines}`),
    refetchInterval: 10_000,
  })
}

export function useVpsNtLog(lines = 200) {
  return useQuery({
    queryKey: ['lab', 'vps', 'nt-log', lines],
    queryFn: () => api.getText(`/vps/nt/log?lines=${lines}`),
    refetchInterval: 10_000,
  })
}

// ── Strategy file management ──────────────────────────────────────────────────

export function useStrategyFiles() {
  return useQuery({
    queryKey: ['lab', 'strategy-files'],
    queryFn: () => api.get<StrategyFile[]>('/strategy-files'),
    refetchInterval: 30_000,
  })
}

export function useStrategyFileSyncStatus() {
  return useQuery({
    queryKey: ['lab', 'strategy-files', 'sync-status'],
    queryFn: () => api.get<StrategyFileSyncStatus[]>('/strategy-files/sync-status'),
    refetchInterval: 60_000,
  })
}

export function useUploadStrategyFile() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ filename, file, overwrite }: { filename: string; file: File; overwrite: boolean }) => {
      const fd = new FormData()
      fd.append('file', file, filename)
      fd.append('filename', filename)
      fd.append('overwrite', String(overwrite))
      const res = await fetch('/api/strategy-files/upload', { method: 'POST', body: fd })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw Object.assign(new Error(err.detail ?? res.statusText), { status: res.status })
      }
      return res.json() as Promise<StrategyFile>
    },
    onSuccess: (_, vars) => {
      toast.success(`${vars.filename} uploaded`)
      qc.invalidateQueries({ queryKey: ['lab', 'strategy-files'] })
      qc.invalidateQueries({ queryKey: ['lab', 'strategy-files', 'sync-status'] })
    },
    onError: (err: Error) => toast.error(`Upload failed: ${err.message}`),
  })
}

export function useDeleteStrategyFile() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (filename: string) => api.delete(`/strategy-files/${encodeURIComponent(filename)}`),
    onSuccess: (_, filename) => {
      toast.success(`${filename} deleted`)
      qc.invalidateQueries({ queryKey: ['lab', 'strategy-files'] })
      qc.invalidateQueries({ queryKey: ['lab', 'strategy-files', 'sync-status'] })
    },
    onError: () => toast.error('Delete failed'),
  })
}

export function useTriggerCompile() {
  return useMutation({
    mutationFn: () => api.post<{ compile_job_id: string }>('/strategy-files/compile', {}),
    onError: () => toast.error('Could not start NT8 compile'),
  })
}

export function useCompileStatus(compileJobId: string | null) {
  return useQuery({
    queryKey: ['lab', 'compile', compileJobId],
    queryFn: () => api.get<CompileJobStatus>(`/strategy-files/compile/${compileJobId}`),
    enabled: !!compileJobId,
    refetchInterval: (query) => {
      const data = query.state.data as CompileJobStatus | undefined
      return data?.status === 'running' ? 2_000 : false
    },
  })
}

export function useTriggerCompileMt5() {
  return useMutation({
    mutationFn: () => api.post<{ compile_job_id: string }>('/strategy-files/compile-mt5', {}),
    onError: () => toast.error('Could not start MT5 compile'),
  })
}

export function useCompileStatusMt5(compileJobId: string | null) {
  return useQuery({
    queryKey: ['lab', 'compile-mt5', compileJobId],
    queryFn: () => api.get<CompileJobStatus>(`/strategy-files/compile-mt5/${compileJobId}`),
    enabled: !!compileJobId,
    refetchInterval: (query) => {
      const data = query.state.data as CompileJobStatus | undefined
      return data?.status === 'running' ? 2_000 : false
    },
  })
}
