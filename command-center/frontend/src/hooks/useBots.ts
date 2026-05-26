import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import type { BotSnapshot } from '@/types'

export function useBotSnapshot() {
  return useQuery({
    queryKey: ['bots', 'snapshot'],
    queryFn: () => api.get<BotSnapshot>('/bots/snapshot'),
    refetchInterval: 60_000,
  })
}

export function useBotLog(botName: string | null) {
  return useQuery({
    queryKey: ['bots', 'log', botName],
    queryFn: () => api.get<string>(`/bots/${encodeURIComponent(botName!)}/log`),
    enabled: !!botName,
    staleTime: 0,
  })
}
