import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api } from '@/api/client'
import type {
  SmartMoneyRunSummary, SmartMoneyRun, Candidate,
  DisqualifiedCandidate, SmartMoneyConfig, ConfigGitStatus, RunProgress,
} from '@/types'

export function useSmartMoneyRuns() {
  return useQuery({
    queryKey: ['smart-money', 'runs'],
    queryFn: () => api.get<SmartMoneyRunSummary[]>('/smart-money/runs'),
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
    queryFn: () =>
      api.get<Candidate>(`/smart-money/runs/${runId}/candidates/${candidateId}`),
    enabled: !!(runId && candidateId),
  })
}

export function useDisqualified(runId: string | null) {
  return useQuery({
    queryKey: ['smart-money', 'disqualified', runId],
    queryFn: () =>
      api.get<DisqualifiedCandidate[]>(`/smart-money/runs/${runId}/disqualified`),
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

export function useRunProgress() {
  return useQuery({
    queryKey: ['smart-money', 'progress'],
    queryFn: () => api.get<RunProgress>('/smart-money/progress'),
    // 1s while running so the address feed feels live; 30s idle to not spam the server.
    refetchInterval: (query) => {
      const status = (query.state.data as RunProgress | undefined)?.status
      return status === 'running' ? 1_000 : 30_000
    },
  })
}

export function useRunPipeline() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<{ status: string; stage: number }>('/smart-money/run', {}),
    onSuccess: () => {
      toast.success('Pipeline started')
      // Optimistic update — Python startup takes 2–3 s, so we fake a "running/starting"
      // state immediately so the terminal appears the moment the 202 comes back.
      qc.setQueryData(['smart-money', 'progress'], (prev: RunProgress | undefined) => ({
        ...(prev ?? {}),
        run_id: '',
        status: 'running' as const,
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
      }))
      // Then trigger a real fetch — will replace the fake state once Python writes progress.json
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
    mutationFn: (cfg: SmartMoneyConfig) =>
      api.put<SmartMoneyConfig>('/smart-money/config', cfg),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['smart-money', 'config'] })
    },
  })
}
