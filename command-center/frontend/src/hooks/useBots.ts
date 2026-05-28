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

// ── Global control actions ────────────────────────────────────────────────────

function useControlAction(action: 'start' | 'stop' | 'restart') {
  const qc = useQueryClient()
  const labels: Record<string, string> = {
    start: 'Bots started',
    stop: 'Bots stopped',
    restart: 'Bots restarted',
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

export const useBotStart   = () => useControlAction('start')
export const useBotStop    = () => useControlAction('stop')
export const useBotRestart = () => useControlAction('restart')

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

// ── Config ───────────────────────────────────────────────────────────────────

import type { BotConfigSections, BotConfigUpdate } from '@/types'

export function useBotConfig(botName: string | null) {
  return useQuery({
    queryKey: ['bots', 'config', botName],
    queryFn: () => api.get<BotConfigSections>(`/bots/${encodeURIComponent(botName!)}/config`),
    enabled: !!botName,
    staleTime: 60_000,
  })
}

type BotCaps = { daily_goal_pct: number; daily_cap_pct: number; weekly_cap_pct: number }

export function useSaveBotCaps() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ botName, caps }: { botName: string; caps: BotCaps }) =>
      api.patch<{ status: string }>(`/bots/${encodeURIComponent(botName)}/caps`, caps),
    onSuccess: (_data, { botName }) => {
      toast.success(`${botName} caps saved`)
      qc.invalidateQueries({ queryKey: ['bots', 'snapshot'] })
    },
    onError: (err, { botName }) => toast.error(`${botName} caps save failed: ${err}`),
  })
}

export function useSaveBotConfig() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ botName, update }: { botName: string; update: BotConfigUpdate }) =>
      api.patch<{ status: string }>(`/bots/${encodeURIComponent(botName)}/config`, update),
    onSuccess: (_data, { botName, update }) => {
      toast.success(update.deploy ? `${botName} deployed — bot restarting` : `${botName} config saved`)
      qc.invalidateQueries({ queryKey: ['bots', 'config', botName] })
      qc.invalidateQueries({ queryKey: ['bots', 'snapshot'] })
    },
    onError: (err, { botName }) => toast.error(`${botName} config save failed: ${err}`),
  })
}
