import { useCallback, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api } from '@/api/client'
import type {
  Strategy, ScanResult, ReconcileResult, DeployJobStatus,
  Ruleset, RulesetCreate, PersonalRulesetPatch,
  BacktestRunRequest, BacktestSummary, BacktestDetail, RunNewsReport, HistoryLimit,
  BrokerProfile, CostLayer, RunRepriceReport,
  LabProgress, SystemHealth,
  SweepRequest, SweepResponse, SweepDetail,
  StackRequest, StackResponse, StackSummary, StackDetail, StackChartSpec,
  StackPreviewRequest, StackPreviewResponse,
  OptimizationRequest, OptimizationSummary, OptimizationDetail,
  InstrumentSummary, RunningJobStatus,
  StrategyFile, StrategyFileSyncStatus, CompileJobStatus,
} from '@/types'
import type { ChartSpec, ChartPage } from '@/components/ChartPanel/types'

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
      const orphans = data.orphans?.length
        ? ` · ${data.orphans.length} orphaned (source deleted — use Reconcile)`
        : ''
      toast.success(`Scanned — ${data.added} added, ${data.updated} updated${orphans}`)
      qc.invalidateQueries({ queryKey: ['lab', 'strategies'] })
    },
    onError: () => toast.error('Strategy scan failed'),
  })
}

export function useReconcileStrategies() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<ReconcileResult>('/strategies/reconcile'),
    onSuccess: (data) => {
      toast.success(`Reconciled — ${data.removed.length} removed from DB + VPS`)
      data.warnings?.forEach((w) => toast.error(w))
      qc.invalidateQueries({ queryKey: ['lab', 'strategies'] })
      qc.invalidateQueries({ queryKey: ['lab', 'strategy-files'] })
      qc.invalidateQueries({ queryKey: ['lab', 'strategy-files', 'sync-status'] })
    },
    onError: () => toast.error('Reconcile failed'),
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

export function usePatchPersonalRuleset() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ rulesetId, body }: { rulesetId: string; body: PersonalRulesetPatch }) =>
      api.patch<Ruleset>(`/rulesets/${rulesetId}`, body),
    onSuccess: () => {
      toast.success('Personal rules updated')
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
    // Poll faster while a run is in progress so live indicators (e.g. the sidebar activity
    // dot and the Runs-tab status) stay current; back off when everything is settled.
    refetchInterval: (query) => {
      const data = query.state.data as BacktestSummary[] | undefined
      return data?.some(r => r.status === 'running') ? 3_000 : 15_000
    },
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

// News/holiday tagging of a completed run's trades — the post-run filter. Static per (run, window),
// so cache indefinitely; re-fetches when pre/post change. `enabled` off until the section is opened.
// Earliest date a backtest of this shape may start. The date picker's `min` comes from
// here rather than a constant in the frontend: the floor is measured off the broker, so a
// hardcoded copy here would drift the moment the terminal changed — and the drift would
// show up as a run the UI accepts and the backend then rejects.
// Long staleTime: it only changes when the broker does, and measuring costs a probe.
export function useHistoryLimit(
  instrument: string | null,
  barType = 'Minute',
  barValue = 15,
  runner = 'python',
) {
  return useQuery({
    queryKey: ['lab', 'history-limit', instrument, barType, barValue, runner],
    queryFn: () => api.get<HistoryLimit | null>(
      `/backtests/history-limit?instrument=${encodeURIComponent(instrument!)}`
      + `&bar_type=${encodeURIComponent(barType)}&bar_value=${barValue}`
      + `&runner=${encodeURIComponent(runner)}`,
    ),
    enabled: !!instrument,
    staleTime: 60 * 60_000,
  })
}

// The broker cost profiles a python run can charge from, with their MEASURED numbers.
// Same rule as `useHistoryLimit` above: the spread is a measurement, so the modal reads it from
// the object the runner bills from instead of carrying its own copy. A hardcoded 0.22 here would
// keep reading 0.22 the day the measurement moved — a page stating a value nothing charges is
// this lab's most-repeated defect.
// Effectively static: it only changes when someone re-measures a broker.
export function useBrokerProfiles() {
  return useQuery({
    queryKey: ['lab', 'broker-profiles'],
    queryFn: () => api.get<BrokerProfile[]>('/backtests/broker-profiles'),
    staleTime: Infinity,
  })
}

export function useRunNews(runId: string | null, pre = 15, post = 30, enabled = true) {
  return useQuery({
    queryKey: ['lab', 'run', runId, 'news', pre, post],
    queryFn: () => api.get<RunNewsReport>(`/backtests/runs/${runId}/news?pre=${pre}&post=${post}`),
    enabled: !!runId && enabled,
    staleTime: Infinity,
    placeholderData: (prev) => prev,   // keep the last window's tags visible while a new pre/post loads (no flicker on slider drag)
  })
}

/** Re-price a completed run's trades at `layers` — the Costs pill on BacktestDetail.
 *
 *  `layers` is joined into the URL and into the query key, so ticking a layer is a new cached
 *  entry rather than a refetch of the same one — flipping a cost back and forth is instant after
 *  the first look. `staleTime: Infinity` because a completed run's trades never change; the only
 *  input is which costs you asked for. */
export function useRunReprice(runId: string | null, layers: CostLayer[], enabled = true) {
  const key = [...layers].sort().join(',')
  return useQuery({
    queryKey: ['lab', 'run', runId, 'repriced', key],
    queryFn: () => api.get<RunRepriceReport>(
      `/backtests/runs/${runId}/repriced?layers=${encodeURIComponent(key)}`),
    // Fetched even with NOTHING ticked: the response carries every layer's own price, which is
    // what the pill shows on each row before you turn any of them on.
    enabled: !!runId && enabled,
    staleTime: Infinity,
    placeholderData: (prev) => prev,   // keep the last set on screen while a new one loads
  })
}

// ChartSpec for the price-chart panel. A run's spec is static, so cache it indefinitely.
// Pass `null` to keep it unfetched until the panel section is opened (candle fetch is heavy).
export function useChartSpec(runId: string | null) {
  return useQuery({
    queryKey: ['lab', 'chart-spec', runId],
    queryFn: () => api.get<ChartSpec>(`/backtests/runs/${runId}/chart-spec`),
    enabled: !!runId,
    staleTime: Infinity,
  })
}

/** Warm the ChartSpec cache in the background as soon as the run page opens, so the Price tab is
 *  a cache hit whenever it is first clicked. The spec is a ~3.5 MB payload (measured on run
 *  432aff31f374) and the browser also has to parse it, so a cold first click paid the whole thing
 *  while the reader watched a skeleton.
 *
 *  `prefetchQuery`, deliberately NOT a page-level `useChartSpec`: prefetch fills the SAME cache
 *  entry without subscribing the page to a multi-megabyte object it never renders — the panel's
 *  own `useChartSpec` reads it straight out. It also swallows its own errors, which is what keeps
 *  a failed prefetch invisible: the panel retries on mount and shows the real error there. */
export function usePrefetchChartSpec(runId: string | null, enabled: boolean) {
  const qc = useQueryClient()
  useEffect(() => {
    if (!runId || !enabled) return
    void qc.prefetchQuery({
      queryKey: ['lab', 'chart-spec', runId],
      queryFn: () => api.get<ChartSpec>(`/backtests/runs/${runId}/chart-spec`),
      staleTime: Infinity,
    })
  }, [qc, runId, enabled])
}

export function useRefreshChartSpec() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (runId: string) =>
      api.get<ChartSpec>(`/backtests/runs/${runId}/chart-spec?refresh=true`),
    onSuccess: (data, runId) => {
      qc.setQueryData(['lab', 'chart-spec', runId], data)
    },
  })
}

// One bounded window of a run's bars: an imperative fetcher (not a query) the ChartPanel calls for
// BOTH of its data paths — a finer-than-base drill-down TF (1m/5m) over the visible window, and a
// scroll-left PAGE of older history at the run's own TF. `available: false` = the feed can't serve
// that window (1m older than the broker's ~35-day 1m history).
//
// `analysis` asks for that window's structure overlays / fair value gaps / blocked / missed setups
// as well. The pager sets it and the drill-down does not: everything except the trades is emitted
// per-window server-side, so without it a layer stops drawing the moment the chart scrolls past the
// shipped candles — see `ChartPage`.
export function useRunCandles(runId: string | null) {
  return useCallback(
    async (tf: string, fromMs: number, toMs: number, analysis = false): Promise<ChartPage> => {
      if (!runId) return { candles: [], available: false, dataStartMs: null, hardEdge: false }
      const q = `tf=${encodeURIComponent(tf)}&from_ms=${Math.round(fromMs)}&to_ms=${Math.round(toMs)}`
        + (analysis ? '&analysis=true' : '')
      const res = await api.get<ChartPage & { data_start_ms: number | null; hard_edge: boolean }>(
        `/backtests/runs/${runId}/candles?${q}`,
      )
      return {
        candles: res.candles ?? [],
        available: !!res.available,
        dataStartMs: res.data_start_ms ?? null,
        hardEdge: !!res.hard_edge,
        overlays: res.overlays,
        blocks: res.blocks,
        misses: res.misses,
        missNoise: res.missNoise,
      }
    },
    [runId],
  )
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
    // No onError toast — see useTriggerOptimization. `api.request` already showed the reason.
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

type RetryVars = { runId: string; evaluateRulesets?: string[]; startDate?: string; endDate?: string }

export function useRetryBacktest() {
  const qc = useQueryClient()
  return useMutation({
    // Accepts a plain run_id (most callers) or a RetryVars object: `evaluateRulesets` when
    // re-firing an optimizer combo with an explicit scoring choice, `startDate`/`endDate` when
    // rerunning a standalone run over a different period. Anything left undefined is omitted from
    // the body, so the backend keeps the run's stored value (and inherit-or-prompts for rulesets).
    mutationFn: (vars: string | RetryVars) => {
      const v: RetryVars = typeof vars === 'string' ? { runId: vars } : vars
      const bodyData: Record<string, unknown> = {}
      if (v.evaluateRulesets !== undefined) bodyData.evaluate_rulesets = v.evaluateRulesets
      if (v.startDate && v.endDate) { bodyData.start_date = v.startDate; bodyData.end_date = v.endDate }
      const body = Object.keys(bodyData).length > 0 ? bodyData : undefined
      return api.post<{ run_id: string; status: string }>(`/backtests/runs/${v.runId}/retry`, body)
    },
    onSuccess: (data) => {
      // The backend wants a ruleset choice before it can score this combo — the caller opens a
      // picker. Don't toast "Rerun started" since nothing started.
      if (data.status === 'needs_ruleset') return
      // A rerun is a trigger like any other: without this the progress query stays on its idle
      // 30s cadence (the last payload was the FAILED attempt), so the running banner showed the
      // previous run's error text for up to half a minute after the rerun had already started.
      _lastTriggerMs = Date.now()
      toast.success('Rerun started')
      qc.invalidateQueries({ queryKey: ['lab', 'progress'] })
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

// ── Portfolio stacks ─────────────────────────────────────────────────────────

export function useStacks() {
  return useQuery({
    queryKey: ['lab', 'stacks'],
    queryFn: () => api.get<StackSummary[]>('/backtests/stacks'),
    refetchInterval: (query) => {
      const data = query.state.data as StackSummary[] | undefined
      return data?.some(s => s.status === 'running') ? 3_000 : 30_000
    },
  })
}

export function useStack(stackId: string | null) {
  return useQuery({
    queryKey: ['lab', 'stack', stackId],
    queryFn: () => api.get<StackDetail>(`/backtests/stacks/${stackId}`),
    enabled: !!stackId,
    refetchInterval: (query) => {
      const data = query.state.data as StackDetail | undefined
      if (!data) return 5_000
      return data.completed_strategies < data.total_strategies ? 3_000 : false
    },
  })
}

// Merged price-chart spec for a stack (shared candles + every completed leg's layer-tagged trades).
// `readyKey` (the completed-leg ids) is in the query key so the spec refetches as legs finish; the
// candle fetch is heavy, so it's kept unfetched until the caller opens the price section (`enabled`).
export function useStackChartSpec(stackId: string | null, readyKey: string, enabled: boolean) {
  return useQuery({
    queryKey: ['lab', 'stack-chart-spec', stackId, readyKey],
    queryFn: () => api.get<StackChartSpec>(`/backtests/stacks/${stackId}/chart-spec`),
    enabled: !!stackId && !!readyKey && enabled,
    staleTime: Infinity,
  })
}

// Live preview: which legs would be reused from an existing completed run vs re-run fresh,
// for the chosen shared settings. Keyed on every setting so it refetches as the user edits.
export function useStackPreview(body: StackPreviewRequest, enabled: boolean) {
  return useQuery({
    queryKey: ['lab', 'stack-preview', body],
    queryFn: () => api.post<StackPreviewResponse>('/backtests/stacks/preview', body),
    enabled,
    staleTime: 30_000,
    retry: false,
  })
}

export function useTriggerStack() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: StackRequest) => api.post<StackResponse>('/backtests/stack', body),
    onSuccess: (res) => {
      toast.success(res.status === 'complete' ? 'Stack assembled from existing runs' : 'Stack started')
      qc.invalidateQueries({ queryKey: ['lab', 'stacks'] })
      qc.invalidateQueries({ queryKey: ['lab', 'running-job'] })
    },
    onError: (e: unknown) => {
      const detail = (e as { detail?: string })?.detail
      toast.error(detail ?? 'Failed to start stack')
    },
  })
}

export function useDeleteStack() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (stackId: string) => api.delete<void>(`/backtests/stacks/${stackId}`),
    onSuccess: () => {
      toast.success('Stack deleted')
      qc.invalidateQueries({ queryKey: ['lab', 'stacks'] })
    },
    onError: (e: unknown) => {
      const msg = (e as { detail?: string })?.detail
      toast.error(msg ?? 'Failed to delete stack')
    },
  })
}

export function useCancelStack() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (stackId: string) =>
      api.post<{ stack_id: string; status: string }>(`/backtests/stacks/${stackId}/cancel`),
    onSuccess: (_data, stackId) => {
      toast.success('Stack cancelled')
      qc.invalidateQueries({ queryKey: ['lab', 'stack', stackId] })
      qc.invalidateQueries({ queryKey: ['lab', 'stacks'] })
      qc.invalidateQueries({ queryKey: ['lab', 'running-job'] })
    },
    onError: (e: unknown) => {
      const msg = (e as { detail?: string })?.detail
      toast.error(msg ?? 'Failed to cancel stack')
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
    // No onError toast on any of these four. `api.request` already toasted the server's own
    // `detail` — "another job is already running", "step must be greater than 0" — and adding a
    // generic one produced TWO toasts where the second, useless one is the one that stays on
    // screen. The reason the first one was never seen is that these handlers read `e.detail`
    // off a plain Error that never had it, so the branch could not fire.
  })
}

export function useCancelOptimization() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (optimizationId: string) =>
      api.post<{ optimization_id: string; status: string; job_stopped?: boolean }>(`/optimizations/${optimizationId}/cancel`),
    onSuccess: (data, optimizationId) => {
      // The row is cancelled either way; whether the RUNNER was reached is a different fact
      // and the one that decides whether the machine is still busy.
      if (data.job_stopped === false) {
        toast.warning('Marked cancelled, but the runner could not be reached — it may still be working')
      } else {
        toast.success('Optimization cancelled')
      }
      qc.invalidateQueries({ queryKey: ['lab', 'optimization', optimizationId] })
      qc.invalidateQueries({ queryKey: ['lab', 'optimizations'] })
      qc.invalidateQueries({ queryKey: ['lab', 'running-job'] })
    },
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
  })
}

export function useRerunOptimization() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (optimizationId: string) =>
      api.post<{ optimization_id: string; status: string; estimated_runs: number }>(`/optimizations/${optimizationId}/rerun`),
    onSuccess: (_data, optimizationId) => {
      toast.success('Re-running optimization')
      qc.invalidateQueries({ queryKey: ['lab', 'optimization', optimizationId] })
      qc.invalidateQueries({ queryKey: ['lab', 'optimizations'] })
      qc.invalidateQueries({ queryKey: ['lab', 'running-job'] })
    },
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
