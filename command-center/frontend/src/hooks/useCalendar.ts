import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import type { CalendarResponse } from '@/types'

// One endpoint: GET /calendar?from&to returns the WHOLE week (all majors, all impacts, all
// categories). The page does currency/impact/category/day filtering client-side, so filter changes
// are instant. Polls every 45s for fresh `actual` values; `useServerClock` below drives the
// countdown between polls.
//
// `refetchMs` exists for the Overview's preview, which shows a title, a time and an impact dot —
// none of which change once an event is published — so it has no reason to re-pull 33 KB every
// 45s. The full page keeps the fast poll because it renders `actual` the moment a release lands.
export function useCalendar(fromMs: number, toMs: number, refetchMs = 45_000) {
  const params = new URLSearchParams({
    from: new Date(fromMs).toISOString(),
    to: new Date(toMs).toISOString(),
  })
  return useQuery({
    queryKey: ['calendar', fromMs, toMs],
    queryFn: () => api.get<CalendarResponse>(`/calendar?${params.toString()}`),
    refetchInterval: refetchMs,
    placeholderData: (prev) => prev, // keep the current week on screen while paging/refetching
  })
}

/** "Now" on the SERVER's clock, ticking every second.
 *
 * Every calendar surface reads the same definition of now, because a countdown and the events
 * it counts down to have to be measured against one clock — two pages disagreeing about the
 * present is how one says "in 2m" while the other has already dropped the event.
 *
 * ⚠ It holds the server/browser OFFSET rather than the timestamp itself. Rendering
 * `server_now_ms` straight from the response freezes the clock between polls, so a countdown
 * sits still and an event that has already fired stays listed as upcoming until the next fetch.
 * With no response yet the offset is 0, i.e. the browser's own clock — a guess, but the only
 * one available, and it is corrected the moment the first response lands. */
export function useServerClock(serverNowMs: number | undefined): number {
  const offsetRef = useRef(0)
  const [nowMs, setNowMs] = useState(() => Date.now())
  useEffect(() => {
    if (serverNowMs) {
      offsetRef.current = serverNowMs - Date.now()
      setNowMs(Date.now() + offsetRef.current)
    }
  }, [serverNowMs])
  useEffect(() => {
    const id = setInterval(() => setNowMs(Date.now() + offsetRef.current), 1000)
    return () => clearInterval(id)
  }, [])
  return nowMs
}
