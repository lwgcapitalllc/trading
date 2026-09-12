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
  AccountStackBasis,
  AccountSync,
  AccountSyncPreview,
  BotAccountAssignResult,
  BotAccountGroup,
  BotAccountRiskPlan,
  BotAccountRiskRequest,
  BotAccountRegistration,
  BotAccountRegistrationWrite,
  BotDeployedVersion,
  BotPromoteJob,
  BotSnapshot,
} from '@/types'

/**
 * The fleet as the trading box reports it, re-read every minute and after every bot action.
 *
 * 🔴 **`silent` since 2026-09-11: it was the one read on the Bots page that still toasted.** A
 * crowded box refuses a connection now and then (backend CLAUDE.md → *The box refuses SSH*), and
 * this read also runs straight after a bot is added — so the add's green toast arrived with a red
 * *502 Cannot reach the VPS* beside it, over a page that already shows the failure in its own
 * error line (with the last good snapshot kept on screen and dated). Reads don't toast.
 *
 * ⚠ **The default retry stays**, unlike the house rule for polls: the failure is a connection the
 * box turned away, which a second ask usually gets through, and with `silent` a retry no longer
 * doubles a toast. `silent` hides the toast, never the error — `error` still reaches the page.
 */
export function useBotSnapshot() {
  return useQuery({
    queryKey: ['bots', 'snapshot'],
    queryFn: () => api.get<BotSnapshot>('/bots/snapshot', { silent: true }),
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
      // 🔴 RETURNED, so the action stays PENDING until the snapshot has been re-read (2026-09-10).
      // Not returned, the row's "Stopping" pill cleared the moment the call came back while the
      // snapshot on screen still said RUNNING — so for one SSH round trip the row offered Stop
      // again on a bot that had just stopped. The deploy watcher holds its finish the same way.
      return qc.invalidateQueries({ queryKey: ['bots', 'snapshot'] })
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

import type {
  BotParamsView,
  BotSettingImportPlan,
  GoLivePlan,
  GoLiveRequest,
  StackSettingImportPlan,
  TelegramUser,
  TelegramUserCreate,
} from '@/types'

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

/**
 * 🔴 **A version read that fails is RENDERED, never toasted (2026-09-11).** The page reads one per
 * bot on every load, each an SSH round trip to the trading box, so a crowded box (which refused a
 * third of connections that day) or a dead one put a toast per bot on the screen, twice with the
 * retry. The pill and the banner show the failure instead (`VersionPill` → Unread). ⚠ No retry
 * here: the backend already asks again for the one failure worth asking again (`services/vps_ssh`).
 */
function readVersion(name: string) {
  return api.get<BotDeployedVersion>(`/bots/${encodeURIComponent(name)}/version`, {
    silent: true,
  })
}

export function useBotVersion(botName: string | null) {
  return useQuery({
    queryKey: ['bots', 'version', botName],
    queryFn: () => readVersion(botName!),
    enabled: !!botName,
    staleTime: 30_000,
    retry: false,
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
      queryFn: () => readVersion(name),
      staleTime: 30_000,
      retry: false,
      // ⚠ The SAME poll rule as `useBotVersion`, through the same function. These share a cache
      // entry per bot, so two different intervals would not merely disagree — whichever query
      // mounted last would decide, and the strip and the card would settle at different times
      // while claiming to be one reading.
      refetchInterval: (q: Query<BotDeployedVersion>) => versionPoll(q.state.data),
    })),
  })
}

/**
 * Every listed bot's most recent deploy job — watched from the PAGE, the one place that is always
 * mounted. The row's version pill and the deploy panel both read what this holds.
 *
 * 🔴 **It lived inside the deploy panel until 2026-09-10, so closing the drawer mid-deploy stopped
 * the polling** — the row kept saying "behind" through the whole deploy, and nothing noticed the
 * finish until the drawer was reopened. Keep it here, and keep it the ONLY watcher: every observer
 * runs its own 1s timer, so a second one polls twice.
 *
 * ⚠ **Addressed by the BOT, not a job id held in component state**, so a drawer opened mid-deploy
 * finds the run already going. `null` is an answer: this backend has run no deploy of that bot.
 *
 * ⚠ **Polled every second only while one runs**; the read is in memory on the backend. `silent`,
 * because a polling read that toasts turns one blip into a queue of popups.
 *
 * 🔴 **A finished deploy is HELD as running until the bot's version has been re-read.** The finish
 * invalidates the version, and for that one SSH round trip every readout still shows the state
 * BEFORE the deploy — the row flashed "behind" straight after a deploy that worked. Awaiting the
 * re-read here means the job and the version change on the same render, on every surface, with no
 * per-surface guard.
 */
export function usePromoteJobs(botNames: string[]) {
  const qc = useQueryClient()
  return useQueries({
    queries: botNames.map((name) => {
      const key = ['bots', 'promote-job', name]
      return {
        queryKey: key,
        queryFn: async () => {
          const next = await api.get<BotPromoteJob | null>(
            `/bots/${encodeURIComponent(name)}/promote/job`,
            { silent: true }
          )
          const prev = qc.getQueryData<BotPromoteJob | null>(key)
          if (
            prev?.status === 'running' &&
            next &&
            next.job_id === prev.job_id &&
            next.status !== 'running'
          ) {
            qc.invalidateQueries({ queryKey: ['bots', 'params', name] })
            qc.invalidateQueries({ queryKey: ['bots', 'snapshot'] })
            // Resolves once the re-read lands, failed or not — it never throws.
            await qc.invalidateQueries({ queryKey: ['bots', 'version', name] })
            if (next.status === 'done') toast.success(`${name}: deployed`)
            else toast.error(`${name}: deploy failed — see the panel`)
          }
          return next
        },
        retry: false,
        staleTime: 0,
        refetchInterval: (q: Query<BotPromoteJob | null>) =>
          q.state.data?.status === 'running' ? 1_000 : false,
      }
    }),
  })
}

/** Start a deploy as a background job. The only action on the panel that changes what a bot
 *  trades. No `onError` toast — `api.post` already surfaces the server's reason (a 409 for a
 *  deploy already running names it). */
export function useStartPromoteJob() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ botName }: { botName: string }) =>
      api.post<BotPromoteJob>(`/bots/${encodeURIComponent(botName)}/promote/job`, {
        pull: true,
        restart: true,
      }),
    onSuccess: (job, { botName }) => {
      // Seed the read so the progress shows on the same frame, then let it poll.
      qc.setQueryData(['bots', 'promote-job', botName], job)
    },
  })
}

/**
 * Change a runtime setting on ONE bot — used for a bot on NO account. A bot on an account changes
 * its risk through `useSaveAccountRisk`, because its share is part of the account's budget and the
 * two must be checked and written together.
 *
 * ⚠ No `onError` toast: `api.patch` already toasts the server's own reason, and a second generic
 * one buried it.
 */
export function useSaveBotRuntime() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      botName,
      values,
    }: {
      botName: string
      values: Record<string, number>
      /** What the toast calls the bot — the key is not a name. */
      display?: string
    }) =>
      api.patch<{ status: string; changed: boolean; detail?: string }>(
        `/bots/${encodeURIComponent(botName)}/runtime`,
        { values, deploy: true }
      ),
    onSuccess: (data, { botName, display }) => {
      const who = display ?? botName
      toast.success(
        data.changed
          ? `${who}: ${data.detail} — applies the next time it has no open trade`
          : `${who} already at those values`
      )
      qc.invalidateQueries({ queryKey: ['bots', 'params', botName] })
      qc.invalidateQueries({ queryKey: ['bots', 'accounts'] })
      qc.invalidateQueries({ queryKey: ['bots', 'snapshot'] })
    },
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
 * What an account's bots run, as the stack builder's starting point — each bot's own settings,
 * chart and risk, the account's ceiling, instrument and cost profile. Read by the Stacks tab when
 * the account panel's "Backtest these bots" opens it.
 *
 * ⚠ **Its key is OUTSIDE `['bots', 'accounts']`**, so an account write's refresh cannot re-read it
 * under a form that is already open — the builder takes its starting values once, and a new answer
 * arriving mid-edit would reshape the legs under the reader's cursor.
 * ⚠ **`gcTime: 0`**: every open is a fresh read. A bot's settings can change between two clicks,
 * and a pre-fill from an old answer would backtest settings the bot no longer has.
 */
export function useAccountStackBasis(account: number | null) {
  return useQuery({
    queryKey: ['stack-basis', account],
    queryFn: () => api.get<AccountStackBasis>(`/bots/accounts/${account}/stack-basis`),
    enabled: account !== null,
    staleTime: Infinity,
    gcTime: 0,
    retry: false,
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
 * ⚠ **Deliberately OUTSIDE the `['bots','accounts']` prefix.** A sync that wrote invalidates that
 * prefix to refresh the page, and a preview under it would be re-asked by the same call — a
 * surprise second scan of the box straight after the one the sync already returned.
 */
export const SYNC_PREVIEW_KEY = ['vps-sync', 'preview'] as const

/**
 * What Sync WOULD change, read off the VPS. Writes nothing (Aaron, 2026-09-10: *"it doesn't show me
 * what it is going to do before I do it"*).
 *
 * 🔴 **Mount it ONLY while the drawer is open.** With `gcTime: 0` the answer is dropped the moment
 * the drawer closes, so every press of Sync VPS is a fresh scan and never a plan read an hour ago.
 * `staleTime: Infinity` then stops it re-asking on its own — no poll, no refetch on focus — because
 * the scan SSHes to the box and attaches to its terminals.
 *
 * ⚠ **`silent`, no retry** — the drawer renders the failure; a toast would say it twice.
 */
export function useSyncPreview(enabled: boolean) {
  return useQuery({
    queryKey: SYNC_PREVIEW_KEY,
    queryFn: () => api.get<AccountSyncPreview>('/bots/accounts/scan', { silent: true }),
    enabled,
    staleTime: Infinity,
    gcTime: 0,
    retry: false,
    refetchOnWindowFocus: false,
  })
}

/**
 * Apply the plan the person was SHOWN. The rules are the server's (`services/account_sync.py`):
 * an account a bot trades is never changed, a terminal is only ever cleared, nothing is removed.
 *
 * 🔴 **It sends the preview's `plan_id`, and the server re-scans and refuses if it moved** — a
 * terminal can switch account between the preview and the press. The refusal comes back as
 * `plan_changed` with the new plan in `now`, which replaces the preview on screen.
 *
 * 🔴 **A MUTATION, fired only by the Sync button under the plan** (*"sync is 100% manually triggered
 * by me only"*). Nothing else calls `mutate`.
 *
 * ⚠ **No retry.** A sync ends in a commit; a failure is a statement and the drawer shows it.
 */
export function useSyncAccounts() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (plan: string) =>
      api.post<AccountSync>('/bots/accounts/registry/sync', { deploy: true, expect_plan: plan }),
    onSuccess: (r) => {
      // `now` IS the fresh preview (re-judged after the writes, or the new plan when refused), so
      // it replaces the one on screen without asking the box a second time.
      qc.setQueryData(SYNC_PREVIEW_KEY, r.now)
      // Only a write moves anything. Re-reading the accounts area after a sync that changed
      // nothing would flash every drawer and heading for no reason.
      if (r.changes.length > 0) qc.invalidateQueries({ queryKey: ['bots', 'accounts'] })
    },
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

// ── An account's risk budget: its cap and every bot's share, as ONE thing ────────
//
// 🔴 **The cap and each share lived behind two writes, and each refused an IMPROVEMENT (fixed
// 2026-09-11).** Fixing an account that did not fit took two saves in the right order and the first
// was often refused. The budget is now planned and saved as one: the server refuses only a change
// that ADDS risk to an account it leaves over the cap, and a cap change needs no restart — each bot
// adopts it the next time it has no open trade.

const riskPlanKey = (account: number | null, body: BotAccountRiskRequest | null) =>
  ['bots', 'accounts', 'risk-plan', account, body] as const

const askRiskPlan = (account: number, body: BotAccountRiskRequest) =>
  api.post<BotAccountRiskPlan>(`/bots/accounts/${account}/risk-plan`, body, { silent: true })

/**
 * What an account's budget WOULD be after a change, and whether a save would be refused. Writes
 * nothing.
 *
 * ⚠ **Under the `['bots','accounts']` prefix on purpose** — a save invalidates that prefix, and a
 * plan describing the budget before the save is the one answer that must not survive it. The
 * endpoint reads local configs, so re-asking costs nothing.
 * ⚠ **`body: null` asks nothing.** Callers pass a body only while there is something to ask about
 * (an edit, an over-subscribed account), so opening a panel never fires a request by itself.
 * ⚠ **`silent`, no retry** — the caller renders a failure next to the thing it is about.
 * ⚠ **`isPlaceholderData` is NOT a fresh answer.** The previous plan is held while the next one is
 * asked, so the line under a box does not flicker — but a Save gated on it must wait for the answer
 * to THIS body.
 */
export function useAccountRiskPlan(account: number | null, body: BotAccountRiskRequest | null) {
  return useQuery({
    queryKey: riskPlanKey(account, body),
    queryFn: () => askRiskPlan(account as number, body as BotAccountRiskRequest),
    enabled: account !== null && body !== null,
    staleTime: 0,
    retry: false,
    placeholderData: (prev) => prev,
  })
}

/**
 * The same plan, asked ONCE when a decision needs it — a bot moved onto an account from its own
 * panel. Imperative because the answer decides what the click does next: fits → move; does not
 * fit → offer the ways to make room. `null` when the server could not answer; the move then goes
 * ahead and the server is the gate.
 */
export function useFetchRiskPlan() {
  const qc = useQueryClient()
  return async (
    account: number,
    body: BotAccountRiskRequest
  ): Promise<BotAccountRiskPlan | null> => {
    try {
      return await qc.fetchQuery({
        queryKey: riskPlanKey(account, body),
        queryFn: () => askRiskPlan(account, body),
        staleTime: 0,
        retry: false,
      })
    } catch {
      return null
    }
  }
}

/**
 * Whether each free bot would fit on an account — one plan per bot, each asking about that bot
 * joining alone. The Add bot list uses it to offer a one-click add or the ways to make room.
 */
export function useJoinPlans(account: number | null, bots: { key: string; risk: number | null }[]) {
  return useQueries({
    queries: bots.map((b) => {
      const body: BotAccountRiskRequest | null =
        b.risk == null ? null : { joining: { [b.key]: b.risk } }
      return {
        queryKey: riskPlanKey(account, body),
        queryFn: () => askRiskPlan(account as number, body as BotAccountRiskRequest),
        enabled: account !== null && body !== null,
        staleTime: 0,
        retry: false,
      }
    }),
  })
}

/**
 * Save an account's budget — the cap, any bot's share, or both — in ONE commit.
 *
 * ⚠ **Only what changed is sent.** `riskCapPct: undefined` leaves the cap alone; `null` means
 * uncapped, a value and not an absence. An empty `shares` is not sent at all.
 * ⚠ `quiet` skips the success toast, for a save that is one step of a bigger gesture (raising the
 * cap to add a bot) whose own toast says what happened.
 */
export function useSaveAccountRisk() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      account,
      riskCapPct,
      shares,
    }: {
      account: number
      riskCapPct?: number | null
      shares?: Record<string, number>
      quiet?: boolean
    }) =>
      api.patch<BotAccountRiskPlan>(`/bots/accounts/${account}/risk`, {
        ...(riskCapPct !== undefined ? { risk_cap_pct: riskCapPct } : {}),
        ...(shares && Object.keys(shares).length > 0 ? { shares } : {}),
        deploy: true,
      }),
    onSuccess: (data, { quiet }) => {
      if (!quiet) {
        if (!data.changed) toast.info(data.detail || 'Nothing to change')
        // The server's own words for WHEN it applies — the half a reader most needs.
        else toast.success(data.detail || 'Saved', { description: data.applies || undefined })
      }
      qc.invalidateQueries({ queryKey: ['bots', 'accounts'] })
      qc.invalidateQueries({ queryKey: ['bots', 'params'] })
      qc.invalidateQueries({ queryKey: ['bots', 'snapshot'] })
    },
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
    mutationFn: ({
      botKey,
      account,
      riskCapPct,
      riskPct,
      confirmLive,
    }: {
      botKey: string
      account: number | null
      /** The cap for an account with NO bot yet — `undefined` sends nothing (not chosen), `null`
       *  sends "uncapped" (chosen). The server refuses it on an account that already has bots. */
      riskCapPct?: number | null
      /** The joining bot's own risk per trade, written in the SAME move — how a bot that does not
       *  fit joins at the room left. `undefined` keeps the bot's own share. */
      riskPct?: number
      /** A move onto a LIVE account must say so, or the server refuses it (409). Sent only after
       *  the reader has confirmed on screen. */
      confirmLive?: boolean
      /** What the toast calls the bot. The server answers with its KEY, which is not a name. */
      display?: string
    }) =>
      api.patch<BotAccountAssignResult>(`/bots/${encodeURIComponent(botKey)}/account`, {
        account,
        ...(riskCapPct !== undefined ? { risk_cap_pct: riskCapPct } : {}),
        ...(riskPct !== undefined ? { risk_pct: riskPct } : {}),
        ...(confirmLive ? { confirm_live: true } : {}),
        deploy: true,
      }),
    onSuccess: (data, vars) => {
      // Never "moved and running" — a bot reads its account at startup, so the honest report is
      // what was written plus what still has to happen.
      const who = vars.display ?? 'The bot'
      const at = vars.riskPct !== undefined ? ` at ${+vars.riskPct.toFixed(2)}% a trade` : ''
      toast.success(
        data.account === null
          ? `${who} taken off the account — it will not start until it is on one again`
          : `${who} added to account ${data.account}${at} — start it to trade`
      )
      // ⚠ A note is what the move could NOT carry — an unregistered account, or one with no
      // recorded symbol suffix. It is raised as a WARNING rather than folded into the success
      // line, because the failure it describes is silent on the box: a bot pointed at a symbol
      // its terminal does not quote connects, warms up and receives no bars.
      // ⚠ `data.info` is deliberately NOT raised (2026-09-11): it is a setting the strategy does not
      // have, which cannot change how it trades, and as a yellow toast it read as a fault.
      for (const note of data.notes ?? []) toast.warning(note)
      qc.invalidateQueries({ queryKey: ['bots', 'accounts'] })
      qc.invalidateQueries({ queryKey: ['bots', 'snapshot'] })
      qc.invalidateQueries({ queryKey: ['bots', 'params'] })
    },
    // ⚠ No `onError` toast: `api.patch` already toasts the server's reason (a running bot, a live
    // account not confirmed, a share that does not fit), and a second one on top buried it.
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

// ── Copying a graded stress test's settings onto a DEMO bot ──────────────────
//
// The pipeline is backtest → stress test → demo → live, and this is the third hop. The one
// promise it makes: the list the reader approves is the change that lands.
//
// 🔴 Both hooks call the SAME endpoint path, and the BACKEND builds the list once for both
// verbs. Nothing here may re-derive, re-sort or re-filter it — a browser-side list beside a
// server-side one is two answers about a live bot, and only one of them was approved.

function importUrl(botName: string, stressTestId: string) {
  return `/bots/${encodeURIComponent(botName)}/settings-from-stress-test/${encodeURIComponent(stressTestId)}`
}

/** What applying this stress test to this bot WOULD do. Writes nothing. */
export function useSettingsImportPreview(botName: string | null, stressTestId: string | null) {
  return useQuery({
    queryKey: ['bots', 'settings-import', botName, stressTestId],
    queryFn: () => api.get<BotSettingImportPlan>(importUrl(botName!, stressTestId!)),
    enabled: !!botName && !!stressTestId,
    // Never cached: it describes a LIVE bot's current settings, and a stale preview is a list
    // that no longer matches what an apply would write — the one thing this flow must not do.
    staleTime: 0,
    gcTime: 0,
    retry: false,
  })
}

/** Write the settings, commit and push. Does NOT restart the bot and does NOT deploy code. */
export function useApplySettingsImport() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ botName, stressTestId }: { botName: string; stressTestId: string }) =>
      api.post<BotSettingImportPlan>(importUrl(botName, stressTestId)),
    onSuccess: (plan, { botName }) => {
      // `applied: false` on a 200 means the bot already matched — a real outcome, not a failure,
      // and reporting it as a success would claim a write that did not happen.
      if (!plan.applied) {
        toast.success(`${botName} already matches this stress test — nothing to write`)
      } else {
        toast.success(
          `${botName}: ${plan.changes.length} setting${plan.changes.length === 1 ? '' : 's'} written — restart the bot for them to take effect`
        )
      }
      qc.invalidateQueries({ queryKey: ['bots', 'params', botName] })
      qc.invalidateQueries({ queryKey: ['bots', 'version', botName] })
      qc.invalidateQueries({ queryKey: ['bots', 'snapshot'] })
      qc.invalidateQueries({ queryKey: ['bots', 'settings-import'] })
    },
    // No toast here: `request` already surfaces the server's own `detail`, which carries the
    // reason (a running bot, a live bot). A second generic toast buries the useful one.
  })
}

// ── A graded STACK's settings, onto every one of its bots at once ─────────────
//
// 🔴 Same contract as the single-bot pair above, and the SAME endpoint path for both verbs: the
// backend plans once and returns one shape, so the list a reader approves is the change that
// lands. Nothing here may re-derive it.

function stackImportUrl(stressTestId: string) {
  return `/bots/stack-settings-from-stress-test/${encodeURIComponent(stressTestId)}`
}

/** What copying this stack's settings onto its bots WOULD do. Writes nothing. */
export function useStackSettingsImportPreview(stressTestId: string | null) {
  return useQuery({
    queryKey: ['bots', 'stack-settings-import', stressTestId],
    queryFn: () => api.get<StackSettingImportPlan>(stackImportUrl(stressTestId!)),
    enabled: !!stressTestId,
    // Never cached, for the reason the single-bot preview is not: it describes LIVE bots' current
    // settings, and a stale list is one that no longer matches what an apply would write.
    staleTime: 0,
    gcTime: 0,
    retry: false,
  })
}

/** Write every leg's settings and the account's risk ceiling. One commit. No restart, no deploy. */
export function useApplyStackSettingsImport() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (stressTestId: string) =>
      api.post<StackSettingImportPlan>(stackImportUrl(stressTestId)),
    onSuccess: (plan) => {
      const n = plan.legs.reduce((sum, leg) => sum + leg.changes.length, 0)
      // `applied: false` on a 200 means the bots already matched. A real outcome, and reporting it
      // as a write that happened would claim an effect nothing had.
      if (!plan.applied) {
        toast.success('These bots already match this stack — nothing to write')
      } else {
        toast.success(
          `${n} setting${n === 1 ? '' : 's'} written across ${plan.legs.length} bot${plan.legs.length === 1 ? '' : 's'} — restart them for it to take effect`
        )
      }
      qc.invalidateQueries({ queryKey: ['bots'] })
    },
    // No toast: `request` already surfaces the server's own reason.
  })
}

// ── Demo to live ─────────────────────────────────────────────────────────────
//
// 🔴 The preview is a MUTATION rather than a query, because it is a POST — the set of bots is
// named in the body, not in the path, and a promotion may never infer its own membership.

/** What promoting these bots onto this live account would do. Writes nothing. */
export function useGoLivePreview() {
  return useMutation({
    mutationFn: (body: { bots: string[]; account: number }) =>
      api.post<GoLivePlan>('/bots/go-live/preview', { ...body, confirm: '' }),
  })
}

/** Move the whole set onto the live account. Refused unless `confirm` matches the plan's own. */
export function useApplyGoLive() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: GoLiveRequest) => api.post<GoLivePlan>('/bots/go-live', body),
    onSuccess: (plan) => {
      // `applied: false` on a 200 means there was nothing to move — every bot was already on that
      // account. A real outcome, and toasting it as a promotion would claim a write nothing made.
      if (!plan.applied) {
        toast.success('These bots are already on that account — nothing to move')
      } else {
        // "Start", not "restart": every bot in the set had to be STOPPED for the move to go
        // through, so there is nothing running to restart.
        toast.success(
          `Moved to live account ${plan.to_account} — start ${plan.moves.length === 1 ? 'it' : 'them'} when you're ready`
        )
      }
      qc.invalidateQueries({ queryKey: ['bots'] })
    },
    // No toast: `request` already surfaces the server's own refusal, which names the rule.
  })
}
