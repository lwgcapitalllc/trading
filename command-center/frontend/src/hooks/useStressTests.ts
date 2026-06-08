import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api } from '@/api/client'
import type { StressTest, StressTestDetail, StressTestCreate, StressTestTriggerResponse, StressLock } from '@/types'

export function useStressTests(runId?: string, grade?: string) {
  const params = new URLSearchParams()
  if (runId) params.set('run_id', runId)
  if (grade) params.set('grade', grade)
  const qs = params.toString()
  return useQuery({
    queryKey: ['stress-tests', runId, grade],
    queryFn: () => api.get<StressTest[]>(`/stress-tests${qs ? '?' + qs : ''}`),
    refetchInterval: 10_000,
  })
}

export function useStressTest(stressTestId: string | null) {
  return useQuery({
    queryKey: ['stress-tests', stressTestId],
    queryFn: () => api.get<StressTestDetail>(`/stress-tests/${stressTestId}`),
    enabled: !!stressTestId,
    refetchInterval: (q) => {
      const data = q.state.data
      if (!data) return 5_000
      if (data.status === 'complete' || data.status.startsWith('failed')) return false
      return 5_000
    },
  })
}

export function useRunStressTest() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: StressTestCreate) =>
      api.post<StressTestTriggerResponse>('/stress-tests/run', body),
    onSuccess: () => {
      toast.success('Stress test started')
      qc.invalidateQueries({ queryKey: ['stress-tests'] })
    },
    onError: () => toast.error('Failed to start stress test'),
  })
}

export function useRunningStressLock() {
  return useQuery({
    queryKey: ['stress-tests', 'running-lock'],
    queryFn: () => api.get<StressLock>('/stress-tests/running-lock'),
    refetchInterval: 5_000,
  })
}

export function useStrategyBestGrades() {
  return useQuery({
    queryKey: ['stress-tests', 'strategy-grades'],
    queryFn: () => api.get<Record<string, { grade: string; stress_test_id: string }>>('/stress-tests/strategy-grades'),
    refetchInterval: 30_000,
  })
}

export function useDeleteStressTest() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (stressTestId: string) => api.delete(`/stress-tests/${stressTestId}`),
    onSuccess: () => {
      toast.success('Stress test deleted')
      qc.invalidateQueries({ queryKey: ['stress-tests'] })
    },
    onError: () => toast.error('Delete failed'),
  })
}
