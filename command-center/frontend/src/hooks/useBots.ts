import { useQuery, useQueries, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api } from '@/api/client'
import type { BotDeployedVersion, BotPromoteResult, BotSnapshot } from '@/types'

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
//
// 🔴 `useBotConfig` / `useSaveBotConfig` / `useSaveBotCaps` were DELETED 2026-08-04 along
// with the three endpoints behind them. Nothing rendered any of them, and two of the
// endpoints restarted a LIVE bot — `PATCH /config` wrote arbitrary sections (including
// strategy params, going around the runtime-editable allowlist) and `PATCH /caps` restarted
// a bot to write a threshold file for a disabled job. Recover with
// `git show 407d716^:command-center/frontend/src/hooks/useBots.ts`.
//
// `useBotParams` reads and `useSaveBotRuntime` writes the one lever that may move — and
// that one does NOT restart the bot.

import type { BotParamsView, TelegramUser, TelegramUserCreate } from '@/types'

// ── Live parameters ──────────────────────────────────────────────────────────
// What a running bot is actually configured with, and the one lever that may move
// under it. The editable set is decided by the BACKEND (services/bot_params.py) —
// this hook never assumes which rows are editable, it reads `row.editable`.

export function useBotParams(botName: string | null) {
  return useQuery({
    queryKey: ['bots', 'params', botName],
    queryFn: () => api.get<BotParamsView>(`/bots/${encodeURIComponent(botName!)}/params`),
    enabled: !!botName,
    staleTime: 30_000,
  })
}

// ── which version is actually deployed, and promoting a new one ────────────────
//
// Read from the VPS, never from the repo. `useBotParams().version` reads the tracked
// config.json, which states INTENT and goes stale the moment the repo moves — it is what
// made "which version is running?" unanswerable. This reads the deployment record written
// beside the bot's frozen code snapshot, so it describes what is on that disk right now.

export function useBotVersion(botName: string | null) {
  return useQuery({
    queryKey: ['bots', 'version', botName],
    queryFn: () => api.get<BotDeployedVersion>(`/bots/${encodeURIComponent(botName!)}/version`),
    enabled: !!botName,
    staleTime: 30_000,
  })
}

/**
 * The same read as `useBotVersion`, for every bot at once — the fleet strip's source.
 *
 * ⚠ It deliberately reuses `useBotVersion`'s query key and query function, so a bot's row in the
 * fleet summary and its own Deployed version card are ONE cache entry. Two fetches of the same
 * fact are two facts that can disagree, and this page's whole job is saying which version is
 * deployed — a strip claiming "1 restart pending" over a card claiming nothing is worse than no
 * strip at all.
 *
 * Each entry stays `undefined` while loading or on error; the caller must count that as UNKNOWN
 * rather than healthy (`no data` and `cannot ask` are not the same value — the rule this repo
 * learned from a bot that was blind for 50 minutes).
 */
export function useBotVersions(botNames: string[]) {
  return useQueries({
    queries: botNames.map(name => ({
      queryKey: ['bots', 'version', name],
      queryFn: () => api.get<BotDeployedVersion>(`/bots/${encodeURIComponent(name)}/version`),
      staleTime: 30_000,
    })),
  })
}

/** Stage + verify a promote without deploying it. The running bot is untouched. */
export function usePreviewPromote() {
  return useMutation({
    mutationFn: ({ botName }: { botName: string }) =>
      api.post<BotPromoteResult>(
        `/bots/${encodeURIComponent(botName)}/promote/preview`, { pull: true, restart: false }),
    onError: (err, { botName }) => toast.error(`${botName}: ${err}`),
  })
}

/** The only action that changes what a bot trades. */
export function usePromoteBot() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ botName, restart }: { botName: string; restart: boolean }) =>
      api.post<BotPromoteResult>(
        `/bots/${encodeURIComponent(botName)}/promote`, { pull: true, restart }),
    onSuccess: (data, { botName }) => {
      if (data.ok) {
        toast.success(data.restarted
          ? `${botName} promoted and restarting`
          : `${botName} promoted — restart it to run the new version`)
      } else {
        // Not a thrown error: promote REFUSES cleanly (dirty tree, a snapshot that will not
        // import) and leaves the running bot alone. That is a result to read, not a crash.
        toast.error(`${botName}: promote refused — see the output`)
      }
      qc.invalidateQueries({ queryKey: ['bots', 'version', botName] })
      qc.invalidateQueries({ queryKey: ['bots', 'params', botName] })
      qc.invalidateQueries({ queryKey: ['bots', 'snapshot'] })
    },
    onError: (err, { botName }) => toast.error(`${botName}: ${err}`),
  })
}

export function useSaveBotRuntime() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ botName, values }: { botName: string; values: Record<string, number> }) =>
      api.patch<{ status: string; changed: boolean; detail?: string }>(
        `/bots/${encodeURIComponent(botName)}/runtime`, { values, deploy: true }),
    onSuccess: (data, { botName }) => {
      toast.success(data.changed
        ? `${botName}: ${data.detail} — applies at the next bar the bot is flat`
        : `${botName} already at those values`)
      qc.invalidateQueries({ queryKey: ['bots', 'params', botName] })
      qc.invalidateQueries({ queryKey: ['bots', 'snapshot'] })
    },
    onError: (err, { botName }) => toast.error(`${botName}: ${err}`),
  })
}

// ── Telegram users ────────────────────────────────────────────────────────────

export function useUsers() {
  return useQuery({
    queryKey: ['bots', 'users'],
    queryFn: () => api.get<TelegramUser[]>('/bots/users'),
    staleTime: 60_000,
  })
}

export function useAddUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: TelegramUserCreate) => api.post<{ status: string }>('/bots/users', body),
    onSuccess: () => {
      toast.success('User added')
      qc.invalidateQueries({ queryKey: ['bots', 'users'] })
    },
    onError: (err) => toast.error(`Add user failed: ${err}`),
  })
}

export function useRemoveUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (chatId: string) => api.delete<{ status: string }>(`/bots/users/${encodeURIComponent(chatId)}`),
    onSuccess: () => {
      toast.success('User removed')
      qc.invalidateQueries({ queryKey: ['bots', 'users'] })
    },
    onError: (err) => toast.error(`Remove user failed: ${err}`),
  })
}

export function useUpdateUserRole() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ chatId, role }: { chatId: string; role: string }) =>
      api.patch<{ status: string }>(`/bots/users/${encodeURIComponent(chatId)}`, { role }),
    onSuccess: () => {
      toast.success('Role updated')
      qc.invalidateQueries({ queryKey: ['bots', 'users'] })
    },
    onError: (err) => toast.error(`Update role failed: ${err}`),
  })
}
