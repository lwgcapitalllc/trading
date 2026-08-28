import {
  useQuery,
  useQueries,
  useMutation,
  useQueryClient,
  type Query,
} from '@tanstack/react-query'
import { toast } from 'sonner'
import { api } from '@/api/client'
import { isRestartPending } from '@/lib/botVersion'
import type {
  BotAccountAssignResult,
  BotAccountCapResult,
  BotAccountGroup,
  BotAccountRegistration,
  BotAccountRegistrationWrite,
  BotDeployedVersion,
  BotPromoteResult,
  BotSnapshot,
} from '@/types'

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

export const useBotStart = () => useControlAction('start')
export const useBotStop = () => useControlAction('stop')
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

export const useBotStartOne = () => useBotAction('start')
export const useBotStopOne = () => useBotAction('stop')
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

/**
 * How often to re-read a deployment record, decided by the RECORD rather than by what the reader
 * just did.
 *
 * 🔴 **This exists because a promote could not settle on screen.** The mutation invalidates this
 * query the moment the HTTP call returns — but a promote ASKS the bot to stop (it polls its
 * instance dir every 10s), waits for it to go, and starts a new process that then stamps its own
 * hash into `bot_state.json`. That is tens of seconds. So the one refetch a promote triggers lands
 * mid-restart, reads the OLD running hash, and — with nothing polling — the page went on claiming
 * *restart pending* over a bot that had already come back, until somebody reloaded. MEASURED
 * 2026-08-28: the strip read `1 restart pending` while the box's own record and the deployment
 * record agreed exactly.
 *
 * ⚠ **The condition is the ANSWER, never the action.** Polling "for a while after a promote" would
 * cover only the restarts this page started — a bot restarted from the CLI, one that crash-looped,
 * or a promote somebody else ran would go on lying just the same. Reading the pending flag off the
 * data means every cause is watched and the poll stops itself the moment the two hashes agree.
 *
 * ⚠ **A settled record is NOT polled, and the interval is 15s rather than the 3s a lab run gets.**
 * This endpoint is one SSH round trip to the trading box per bot — MEASURED 4.5s — so a poll here
 * is not free the way a local DB read is, and it multiplies by the fleet. 15s is comfortably inside
 * the restart it is watching and leaves the connection idle most of the time.
 *
 * ⚠ **An idle page that has NOT seen a pending restart still refetches on window focus** (the app's
 * global 30s `staleTime`), which is what covers a promote made somewhere else while this tab sat in
 * the background. Nothing polls for a state it has never seen; that is the deliberate limit.
 */
function versionPoll(v: BotDeployedVersion | undefined): number | false {
  return isRestartPending(v) ? 15_000 : false
}

export function useBotVersion(botName: string | null) {
  return useQuery({
    queryKey: ['bots', 'version', botName],
    queryFn: () => api.get<BotDeployedVersion>(`/bots/${encodeURIComponent(botName!)}/version`),
    enabled: !!botName,
    staleTime: 30_000,
    refetchInterval: (q) => versionPoll(q.state.data),
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
    queries: botNames.map((name) => ({
      queryKey: ['bots', 'version', name],
      queryFn: () => api.get<BotDeployedVersion>(`/bots/${encodeURIComponent(name)}/version`),
      staleTime: 30_000,
      // ⚠ The SAME poll rule as `useBotVersion`, through the same function. These share a cache
      // entry per bot, so two different intervals would not merely disagree — whichever query
      // mounted last would decide, and the strip and the card would settle at different times
      // while claiming to be one reading.
      refetchInterval: (q: Query<BotDeployedVersion>) => versionPoll(q.state.data),
    })),
  })
}

/** Stage + verify a promote without deploying it. The running bot is untouched. */
export function usePreviewPromote() {
  return useMutation({
    mutationFn: ({ botName }: { botName: string }) =>
      api.post<BotPromoteResult>(`/bots/${encodeURIComponent(botName)}/promote/preview`, {
        pull: true,
        restart: false,
      }),
    onError: (err, { botName }) => toast.error(`${botName}: ${err}`),
  })
}

/** The only action that changes what a bot trades. */
export function usePromoteBot() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ botName, restart }: { botName: string; restart: boolean }) =>
      api.post<BotPromoteResult>(`/bots/${encodeURIComponent(botName)}/promote`, {
        pull: true,
        restart,
      }),
    onSuccess: (data, { botName }) => {
      if (data.ok) {
        toast.success(
          data.restarted
            ? `${botName} promoted and restarting`
            : `${botName} promoted — restart it to run the new version`
        )
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
        `/bots/${encodeURIComponent(botName)}/runtime`,
        { values, deploy: true }
      ),
    onSuccess: (data, { botName }) => {
      toast.success(
        data.changed
          ? `${botName}: ${data.detail} — applies at the next bar the bot is flat`
          : `${botName} already at those values`
      )
      qc.invalidateQueries({ queryKey: ['bots', 'params', botName] })
      qc.invalidateQueries({ queryKey: ['bots', 'snapshot'] })
    },
    onError: (err, { botName }) => toast.error(`${botName}: ${err}`),
  })
}

// ── Accounts — the shared-balance view and its one ceiling ────────────────────

/**
 * Which bots share a trading account.
 *
 * Cheap and VPS-free — the backend reads the same instance configs the bots read — so this
 * still answers while the box is unreachable. Whether a bot is RUNNING comes from the
 * snapshot, and the page joins the two on `key`; asking one endpoint for both would make a
 * grouping question depend on an SSH round trip it does not need.
 */
export function useBotAccounts() {
  return useQuery({
    queryKey: ['bots', 'accounts'],
    queryFn: () => api.get<BotAccountGroup[]>('/bots/accounts'),
    refetchInterval: 60_000,
  })
}

/**
 * The broker accounts a bot can be put ON.
 *
 * 🔴 **This is the half `useBotAccounts` structurally cannot answer.** That one derives the
 * grouping from the instance configs, which is right and must stay right — but it can only see
 * accounts some bot is ALREADY on, so the first bot on a new account was unmovable from this page
 * and had to be moved by hand-editing a config on the VPS.
 *
 * ⚠ **It is a SEPARATE query from `useBotAccounts`, not a field on it.** The registry is a local
 * file and always readable; the grouping needs no VPS either, but `has_password` does — so folding
 * them together would make the account list depend on the box being reachable.
 */
export function useRegisteredAccounts() {
  return useQuery({
    queryKey: ['bots', 'accounts', 'registry'],
    queryFn: () => api.get<BotAccountRegistration[]>('/bots/accounts/registry'),
    staleTime: 60_000,
  })
}

/**
 * Add a broker account, or replace the registered facts about one.
 *
 * ⚠ **A password sent here goes to a DIFFERENT FILE on a different machine** — the git-ignored
 * `algos/credentials.json` on the VPS — and is never returned by any endpoint. The registry itself
 * is git-tracked and holds no secret.
 */
export function useRegisterAccount() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: BotAccountRegistrationWrite) =>
      api.put<BotAccountRegistration>(`/bots/accounts/registry/${body.account}`, {
        deploy: true,
        ...body,
      }),
    onSuccess: (data) => {
      toast.success(`Account ${data.account} saved`)
      qc.invalidateQueries({ queryKey: ['bots', 'accounts'] })
    },
  })
}

/**
 * Forget a broker account. Refused (409) while a bot still names it — that bot would go on trading
 * an account this page could no longer describe.
 */
export function useUnregisterAccount() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (account: number) =>
      api.delete<{ status: string }>(`/bots/accounts/registry/${account}`),
    onSuccess: () => {
      toast.success('Account removed from the list')
      qc.invalidateQueries({ queryKey: ['bots', 'accounts'] })
    },
  })
}

/**
 * Store one account's MT5 password on the VPS.
 *
 * **Write-only, by design — there is no read counterpart and there must not be one.** The page
 * needs to know whether a password EXISTS, which `useRegisteredAccounts` answers as a boolean.
 */
export function useSetAccountPassword() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ account, password }: { account: number; password: string }) =>
      api.put(`/bots/accounts/registry/${account}/password`, { password }),
    onSuccess: () => {
      toast.success('Password saved on the VPS')
      qc.invalidateQueries({ queryKey: ['bots', 'accounts', 'registry'] })
    },
  })
}

/**
 * Set (or clear) the account-level risk cap across every bot on one account.
 *
 * `riskCapPct: null` means UNCAPPED, which is a value rather than "leave it alone" — there is
 * deliberately no separate clear action, so the absent value keeps meaning the one thing.
 *
 * The toast always says a restart is needed when something was written: the cap is read by the
 * order bridge at startup and is not runtime-reloadable, so a written-but-not-running cap is
 * the one state that reads as protected and is not.
 */
export function useSetAccountRiskCap() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ account, riskCapPct }: { account: number; riskCapPct: number | null }) =>
      api.patch<BotAccountCapResult>(`/bots/accounts/${account}/risk-cap`, {
        risk_cap_pct: riskCapPct,
        deploy: true,
      }),
    onSuccess: (data) => {
      if (!data.changed) {
        toast.info(data.detail || 'Already at that cap')
      } else {
        toast.success(
          `${data.detail} — restart ${data.updated.length === 1 ? 'it' : 'them'} to apply`
        )
      }
      qc.invalidateQueries({ queryKey: ['bots', 'accounts'] })
      qc.invalidateQueries({ queryKey: ['bots', 'params'] })
    },
    onError: (err) => toast.error(`Risk cap: ${err}`),
  })
}

/**
 * Move one bot onto an account, or off one (`account: null` = the bench).
 *
 * ⚠ **It invalidates the SNAPSHOT as well as the accounts list**, and that is not belt-and-braces:
 * the Accounts tab reads running state from the snapshot and joins it on `key`, so a bot that
 * moved cards while the snapshot still described it under the old one would show a stale State
 * beside a fresh account. The two queries have different sources and only one of them changed.
 */
export function useAssignBotAccount() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ botKey, account }: { botKey: string; account: number | null }) =>
      api.patch<BotAccountAssignResult>(`/bots/${encodeURIComponent(botKey)}/account`, {
        account,
        deploy: true,
      }),
    onSuccess: (data) => {
      // Never "moved and running" — a bot reads its account at startup, so the honest report is
      // what was written plus what still has to happen. Same rule as the risk cap above.
      toast.success(
        data.account === null
          ? `${data.bot} taken off the account — it will not start until it is on one again`
          : `${data.bot} added to account ${data.account} — start it to trade`
      )
      // ⚠ A note is what the move could NOT carry — an unregistered account, or one with no
      // recorded symbol suffix. It is raised as a WARNING rather than folded into the success
      // line, because the failure it describes is silent on the box: a bot pointed at a symbol
      // its terminal does not quote connects, warms up and receives no bars.
      for (const note of data.notes ?? []) toast.warning(note)
      qc.invalidateQueries({ queryKey: ['bots', 'accounts'] })
      qc.invalidateQueries({ queryKey: ['bots', 'snapshot'] })
      qc.invalidateQueries({ queryKey: ['bots', 'params'] })
    },
    onError: (err) => toast.error(`Move: ${err}`),
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
    mutationFn: (chatId: string) =>
      api.delete<{ status: string }>(`/bots/users/${encodeURIComponent(chatId)}`),
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
