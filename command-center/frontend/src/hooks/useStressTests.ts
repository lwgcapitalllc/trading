import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'

export function useStressTestResults() {
  return useQuery({
    queryKey: ['stress-tests', 'results'],
    queryFn: () => api.get<unknown[]>('/stress-tests/results'),
  })
}
