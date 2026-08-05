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
    onSuccess: (data) => {
      toast.success('Stress test started')
      // The server knows things the form cannot — chiefly that this many windows over this many
      // trades can only ever return "not assessable". Saying so at the moment work starts is the
      // difference between a wasted hour and a different choice.
      for (const w of data.warnings ?? []) toast.warning(w, { duration: 12_000 })
      qc.invalidateQueries({ queryKey: ['stress-tests'] })
      qc.invalidateQueries({ queryKey: ['lab', 'running-job'] })
    },
    // `api.request` already toasts the server's own message (ApiError carries `detail`), so a
    // second generic toast here would restate it on top of the useful one.
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

export function useCancelStressTest() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (stressTestId: string) =>
      api.post<{ children_cancelled: number; job_stopped: boolean }>(`/stress-tests/${stressTestId}/cancel`, {}),
    onSuccess: (data) => {
      // `job_stopped: false` means the row is cancelled but the runner could not be told, so the
      // platform may still be busy. Two different facts; only one of them means you can start
      // something else — the same distinction the optimizer's cancel reports.
      if (data.job_stopped) toast.success('Stress test cancelled')
      else toast.error('Cancelled, but the runner could not be reached — the platform may still be busy')
      qc.invalidateQueries({ queryKey: ['stress-tests'] })
      qc.invalidateQueries({ queryKey: ['lab', 'running-job'] })
    },
    onError: () => toast.error('Cancel failed'),
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
