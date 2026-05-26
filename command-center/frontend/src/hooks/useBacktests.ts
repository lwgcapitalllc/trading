import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'

export function useBacktestRuns() {
  return useQuery({
    queryKey: ['backtests', 'runs'],
    queryFn: () => api.get<unknown[]>('/backtests/runs'),
  })
}
