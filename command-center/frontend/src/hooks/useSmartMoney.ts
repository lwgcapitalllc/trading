import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import type {
  SmartMoneyRunSummary, SmartMoneyRun, Candidate,
  DisqualifiedCandidate, SmartMoneyConfig, ConfigGitStatus,
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
