import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api } from '@/api/client'
import type {
  Strategy, ScanResult,
  Firm, FirmCreate,
  BacktestRunRequest, BacktestSummary, BacktestDetail,
  LabProgress, SystemHealth,
  SweepRequest, SweepResponse, SweepDetail,
  OptimizationRequest, OptimizationSummary, OptimizationDetail,
  InstrumentSummary,
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

// ── Firms ──────────────────────────────────────────────────────────────────────

export function useFirms() {
  return useQuery({
    queryKey: ['lab', 'firms'],
    queryFn: () => api.get<Firm[]>('/firms'),
  })
}

export function useCreateFirm() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: FirmCreate) => api.post<Firm>('/firms', body),
    onSuccess: () => {
      toast.success('Firm created')
      qc.invalidateQueries({ queryKey: ['lab', 'firms'] })
    },
    onError: () => toast.error('Failed to create firm'),
  })
}

export function useUpdateFirm() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ firmId, body }: { firmId: string; body: FirmCreate }) =>
      api.put<Firm>(`/firms/${firmId}`, body),
    onSuccess: () => {
      toast.success('Firm updated')
      qc.invalidateQueries({ queryKey: ['lab', 'firms'] })
    },
    onError: () => toast.error('Failed to update firm'),
  })
}

export function useDeleteFirm() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (firmId: string) => api.delete<void>(`/firms/${firmId}`),
    onSuccess: () => {
      toast.success('Firm deleted')
      qc.invalidateQueries({ queryKey: ['lab', 'firms'] })
    },
    onError: () => toast.error('Failed to delete firm'),
  })
}

// ── Backtest Runs ──────────────────────────────────────────────────────────────

export function useBacktestRuns(filters?: {
  strategy_id?: string
  firm_id?: string
  status?: string
}) {
  const params = new URLSearchParams()
  if (filters?.strategy_id) params.set('strategy_id', filters.strategy_id)
  if (filters?.firm_id)     params.set('firm_id',     filters.firm_id)
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

// Module-level timestamp: keeps progress polling fast for 60s after a trigger
// so the UI reflects state changes while the VPS agent starts the job.
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
    },
    onError: () => toast.error('Failed to start backtest'),
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

export function useStopBacktest() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (runId: string) =>
      api.post<{ run_id: string; status: string }>(`/backtests/runs/${runId}/stop`),
    onSuccess: (_data, runId) => {
      toast.success('Backtest cancelled')
      qc.invalidateQueries({ queryKey: ['lab', 'run', runId] })
      qc.invalidateQueries({ queryKey: ['lab', 'runs'] })
    },
    onError: () => toast.error('Failed to stop backtest'),
  })
}

export function useRetryBacktest() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (runId: string) =>
      api.post<{ run_id: string; status: string }>(`/backtests/runs/${runId}/retry`),
    onSuccess: () => {
      toast.success('Retry started')
      qc.invalidateQueries({ queryKey: ['lab', 'runs'] })
    },
    onError: () => toast.error('Failed to retry backtest'),
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
    onError: () => toast.error('Chart reload failed — check VPS agent and NT8 SA'),
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

export function useStartVpsAgent() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<{ status: string; output: string }>('/system/vps-agent/start'),
    onSuccess: () => {
      toast.success('VPS agent starting…')
      setTimeout(() => qc.invalidateQueries({ queryKey: ['system', 'health'] }), 4_000)
    },
    onError: () => toast.error('Failed to start VPS agent — is SSH up?'),
  })
}

// ── Sweeps ─────────────────────────────────────────────────────────────────────

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

export function useTriggerSweep() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: SweepRequest) => api.post<SweepResponse>('/backtests/sweep', body),
    onSuccess: () => {
      toast.success('Sweep started')
      qc.invalidateQueries({ queryKey: ['lab', 'runs'] })
    },
    onError: () => toast.error('Failed to start sweep'),
  })
}

// ── Optimizations ──────────────────────────────────────────────────────────────

export function useOptimizations(strategyId?: string) {
  const qs = strategyId ? `?strategy_id=${strategyId}` : ''
  return useQuery({
    queryKey: ['lab', 'optimizations', strategyId ?? 'all'],
    queryFn: () => api.get<OptimizationSummary[]>(`/optimizations${qs}`),
  })
}

export function useOptimization(optimizationId: string | null) {
  return useQuery({
    queryKey: ['lab', 'optimization', optimizationId],
    queryFn: () => api.get<OptimizationDetail>(`/optimizations/${optimizationId}`),
    enabled: !!optimizationId,
    refetchInterval: (query) => {
      const data = query.state.data as OptimizationDetail | undefined
      return data?.status === 'running' ? 3_000 : false
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
    },
    onError: () => toast.error('Failed to start optimization'),
  })
}

// ── Instrument Summary ─────────────────────────────────────────────────────────

export function useInstrumentSummary(
  strategyId: string | null,
  firmId?: string,
  startDate?: string,
  endDate?: string,
) {
  const params = new URLSearchParams()
  if (firmId)    params.set('firm_id',    firmId)
  if (startDate) params.set('start_date', startDate)
  if (endDate)   params.set('end_date',   endDate)
  const qs = params.toString()

  return useQuery({
    queryKey: ['lab', 'instrument-summary', strategyId, firmId, startDate, endDate],
    queryFn: () => api.get<InstrumentSummary>(`/strategies/${strategyId}/instrument_summary${qs ? `?${qs}` : ''}`),
    enabled: !!strategyId,
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
