import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import type { CalendarResponse } from '@/types'

// One endpoint: GET /calendar?from&to returns the WHOLE week (all majors, all impacts, all
// categories). The page does currency/impact/category/day filtering client-side, so filter changes
// are instant. Polls every 45s for fresh `actual` values; a local 1s ticker in the page drives the
// countdown between polls (see Calendar.tsx).
export function useCalendar(fromMs: number, toMs: number) {
  const params = new URLSearchParams({
    from: new Date(fromMs).toISOString(),
    to: new Date(toMs).toISOString(),
  })
  return useQuery({
    queryKey: ['calendar', fromMs, toMs],
    queryFn: () => api.get<CalendarResponse>(`/calendar?${params.toString()}`),
    refetchInterval: 45_000,
    placeholderData: (prev) => prev, // keep the current week on screen while paging/refetching
  })
}
