import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
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
    queryFn: () => api.getText(`/bots/${encodeURIComponent(botName!)}/log`),
    enabled: !!botName,
    staleTime: 0,
  })
}

type ControlResult = { status: string; output: string }

function useControlAction(action: 'start' | 'stop' | 'restart' | 'emergency') {
  const qc = useQueryClient()
  const labels: Record<string, string> = {
    start: 'Bots started',
    stop: 'Bots stopped',
    restart: 'Bots restarted',
    emergency: 'Emergency stop sent',
  }
  return useMutation({
    mutationFn: () => api.post<ControlResult>(`/bots/${action}`),
    onSuccess: () => {
      toast.success(labels[action])
      qc.invalidateQueries({ queryKey: ['bots', 'snapshot'] })
    },
    onError: (err) => {
      toast.error(`${labels[action]} failed: ${err}`)
    },
  })
}

export const useBotStart     = () => useControlAction('start')
export const useBotStop      = () => useControlAction('stop')
export const useBotRestart   = () => useControlAction('restart')
export const useBotEmergency = () => useControlAction('emergency')

// ── Per-bot control actions ───────────────────────────────────────────────────

function useBotAction(action: 'start' | 'stop' | 'restart') {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (botName: string) =>
      api.post<ControlResult>(`/bots/${encodeURIComponent(botName)}/${action}`),
    onSuccess: (_data, botName) => {
      const label = { start: 'started', stop: 'stopped', restart: 'restarted' }[action]
      toast.success(`${botName} ${label}`)
      qc.invalidateQueries({ queryKey: ['bots', 'snapshot'] })
    },
    onError: (err, botName) => {
      toast.error(`${botName} ${action} failed: ${err}`)
    },
  })
}

export const useBotStartOne   = () => useBotAction('start')
export const useBotStopOne    = () => useBotAction('stop')
export const useBotRestartOne = () => useBotAction('restart')
