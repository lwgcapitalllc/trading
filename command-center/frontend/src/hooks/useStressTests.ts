import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api } from '@/api/client'
import type {
  Gradable,
  StressTest,
  StressTestDetail,
  StressTestCreate,
  StressTestTriggerResponse,
  StressLock,
} from '@/types'

/** The stress-test LIST, narrowed to one run, one stack or one grade — newest first.
 *
 *  ⚠ The key sits under `'list'` rather than putting a run id at position 1, where a stress test's
 *  own detail keeps ITS id: the delete refresh excludes an entry by comparing that slot. */
export function useStressTests(filter: { runId?: string; stackId?: string; grade?: string } = {}) {
  const { runId, stackId, grade } = filter
  const params = new URLSearchParams()
  if (runId) params.set('run_id', runId)
  if (stackId) params.set('stack_id', stackId)
  if (grade) params.set('grade', grade)
  const qs = params.toString()
  return useQuery({
    queryKey: ['stress-tests', 'list', { runId, stackId, grade }],
    queryFn: () => api.get<StressTest[]>(`/stress-tests${qs ? '?' + qs : ''}`),
    refetchInterval: 10_000,
  })
}

/** Can this stack (or run) be stress tested, and if not, why — asked BEFORE the reader commits.
 *
 * 🔴 **It exists because the refusal used to arrive after the click.** Promoting a stack was
 * offered on stacks that cannot be graded, and nothing on the page could tell: the stack reported
 * 272 combined trades and its contention data as available, so every check the screen could make
 * PASSED. What was missing was a file only the backend can see, and the reader found out by
 * waiting for a 400.
 *
 * 🔴 **The answer comes from the SAME resolver that would refuse the run.** Re-deriving the
 * question here would be a second opinion about a stack somebody is about to spend an hour on,
 * and the copy that goes stale is always the one the button reads.
 *
 * ⚠ **`gradable: false` is a 200.** The endpoint answers rather than erroring, so this never
 * enters the error branch and a legitimate question never looks like a broken page.
 */
export function useGradable(stackId: string | null) {
  return useQuery({
    queryKey: ['stress-tests', 'gradable', stackId],
    queryFn: () =>
      api.get<Gradable>(`/stress-tests/gradable?stack_id=${encodeURIComponent(stackId as string)}`),
    enabled: !!stackId,
    // A stack that finishes replaying becomes gradable, so a stale "no" would outlive its reason.
    staleTime: 0,
    gcTime: 0,
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
    queryFn: () =>
      api.get<Record<string, { grade: string; stress_test_id: string }>>(
        '/stress-tests/strategy-grades'
      ),
    refetchInterval: 30_000,
  })
}

export function useCancelStressTest() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (stressTestId: string) =>
      api.post<{ children_cancelled: number; job_stopped: boolean }>(
        `/stress-tests/${stressTestId}/cancel`,
        {}
      ),
    onSuccess: (data) => {
      // `job_stopped: false` means the row is cancelled but the runner could not be told, so the
      // platform may still be busy. Two different facts; only one of them means you can start
      // something else — the same distinction the optimizer's cancel reports.
      if (data.job_stopped) toast.success('Stress test cancelled')
      else
        toast.error(
          'Cancelled, but the runner could not be reached — the platform may still be busy'
        )
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
    onSuccess: (_, stressTestId) => {
      toast.success('Stress test deleted')
      // 🔴 The list and the detail share the `['stress-tests']` prefix, so refreshing the prefix
      // re-asked the server for the test it had just deleted — while its page was still mounted
      // — and the 404 toasted as a red "Stress test not found" on every delete. Everything under
      // the prefix refreshes EXCEPT the deleted test's own entry.
      // ⚠ Excluded, never removed: removing it while its page is still mounted makes that page's
      // next render rebuild the entry and fetch it — the same 404 by a different route. The page
      // leaves on its own; the orphaned entry is collected once nothing reads it.
      qc.invalidateQueries({
        queryKey: ['stress-tests'],
        predicate: (q) => q.queryKey[1] !== stressTestId,
      })
    },
    // No onError toast — `api.request` already shows the server's own reason.
  })
}
