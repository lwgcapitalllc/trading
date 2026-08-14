import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api } from '@/api/client'
import type {
  SmartMoneyRunSummary,
  SmartMoneyRun,
  Candidate,
  DisqualifiedCandidate,
  SmartMoneyConfig,
  ConfigGitStatus,
  RunProgress,
  CacheStats,
  CacheClearResult,
} from '@/types'

// Module-level timestamp — shared between useRunProgress and useRunPipeline so
// the polling interval stays fast for 60s after a trigger even if the cache
// gets overwritten with the old completed state before Python starts writing.
let _lastTriggerMs = 0

// `enabled` exists so a caller behind a feature flag can stop the fetch as well
// as the render — the Overview passes FEATURES.smartMoney.
export function useSmartMoneyRuns(enabled = true) {
  return useQuery({
    queryKey: ['smart-money', 'runs'],
    queryFn: () => api.get<SmartMoneyRunSummary[]>('/smart-money/runs'),
    enabled,
  })
}

export function useSmartMoneyRun(runId: string | null) {
  return useQuery({
    queryKey: ['smart-money', 'run', runId],
    queryFn: () => api.get<SmartMoneyRun>(`/smart-money/runs/${runId}`),
    enabled: !!runId,
  })
}

export function useCandidates(runId: string | null) {
  return useQuery({
    queryKey: ['smart-money', 'candidates', runId],
    queryFn: () => api.get<Candidate[]>(`/smart-money/runs/${runId}/candidates`),
    enabled: !!runId,
  })
}

export function useCandidate(runId: string | null, candidateId: string | null) {
  return useQuery({
    queryKey: ['smart-money', 'candidate', runId, candidateId],
    queryFn: () => api.get<Candidate>(`/smart-money/runs/${runId}/candidates/${candidateId}`),
    enabled: !!(runId && candidateId),
  })
}

export function useDisqualified(runId: string | null) {
  return useQuery({
    queryKey: ['smart-money', 'disqualified', runId],
    queryFn: () => api.get<DisqualifiedCandidate[]>(`/smart-money/runs/${runId}/disqualified`),
    enabled: !!runId,
  })
}

export function useSmartMoneyConfig() {
  return useQuery({
    queryKey: ['smart-money', 'config'],
    queryFn: () => api.get<SmartMoneyConfig>('/smart-money/config'),
  })
}

export function useConfigGitStatus() {
  return useQuery({
    queryKey: ['smart-money', 'config', 'git-status'],
    queryFn: () => api.get<ConfigGitStatus>('/smart-money/config/git-status'),
    refetchInterval: 30_000,
  })
}

export function useRunProgress(enabled = true) {
  return useQuery({
    queryKey: ['smart-money', 'progress'],
    queryFn: () => api.get<RunProgress>('/smart-money/progress'),
    enabled,
    refetchInterval: (query) => {
      const status = (query.state.data as RunProgress | undefined)?.status
      // For 60s after a trigger, always poll at 1.5s regardless of status —
      // this bridges the gap while Python is importing/starting (10–15s) and
      // prevents the interval from falling back to 30s after the first poll
      // returns the old completed state.
      if (Date.now() - _lastTriggerMs < 60_000) return 1_500
      return status === 'running' ? 1_000 : 30_000
    },
  })
}

export function useRunPipeline() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (profile: 'bot' | 'human' | null) =>
      api.post<{ status: string; stage: number; profile: string | null }>('/smart-money/run', {
        profile,
      }),
    onSuccess: (_data, profile) => {
      _lastTriggerMs = Date.now()
      toast.success(`Pipeline started${profile ? ` (${profile} profile)` : ''}`)
      // Kick off a poll — the component uses local isStarting state for the
      // immediate terminal display so we don't need setQueryData here.
      qc.invalidateQueries({ queryKey: ['smart-money', 'progress'] })
    },
  })
}

export function useStopPipeline() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<{ status: string; killed: boolean }>('/smart-money/stop', {}),
    onSuccess: () => {
      toast.success('Pipeline stopped')
      qc.invalidateQueries({ queryKey: ['smart-money', 'progress'] })
    },
  })
}

export function useSaveConfig() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (cfg: SmartMoneyConfig) => api.put<SmartMoneyConfig>('/smart-money/config', cfg),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['smart-money', 'config'] })
    },
  })
}

export function useCacheStats() {
  return useQuery({
    queryKey: ['smart-money', 'cache', 'stats'],
    queryFn: () => api.get<CacheStats>('/smart-money/cache/stats'),
    refetchInterval: 60_000,
  })
}

export function useClearCache() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.delete<CacheClearResult>('/smart-money/cache'),
    onSuccess: (data) => {
      const n = data.cleared
      toast.success(`Cache cleared — ${n} wallet${n !== 1 ? 's' : ''} removed`)
      qc.invalidateQueries({ queryKey: ['smart-money', 'cache'] })
    },
    onError: () => {
      toast.error('Failed to clear cache')
    },
  })
}
