import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api } from '@/api/client'
import type { QueueItem } from '@/types'

export function useQueue() {
  return useQuery({
    queryKey: ['queue'],
    queryFn: () => api.get<QueueItem[]>('/queue'),
    refetchInterval: 5_000,
  })
}

export function useEnqueueOptimization() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (optimization_id: string) =>
      api.post<{ queue_id: string; status: string }>('/queue/optimization', { optimization_id }),
    onSuccess: () => {
      toast.success('Optimization added to queue')
      qc.invalidateQueries({ queryKey: ['queue'] })
    },
    onError: () => toast.error('Failed to queue optimization'),
  })
}

export function useEnqueueStressTest() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { stress_test_id: string; include_walk_forward?: boolean; include_sensitivity?: boolean }) =>
      api.post<{ queue_id: string; status: string }>('/queue/stress-test', body),
    onSuccess: () => {
      toast.success('Stress test added to queue')
      qc.invalidateQueries({ queryKey: ['queue'] })
    },
    onError: () => toast.error('Failed to queue stress test'),
  })
}

export function useDeleteQueueItem() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (queue_id: string) =>
      api.delete<void>(`/queue/${queue_id}`),
    onSuccess: () => {
      toast.success('Removed from queue')
      qc.invalidateQueries({ queryKey: ['queue'] })
    },
    onError: () => toast.error('Could not remove — item may already be running'),
  })
}
