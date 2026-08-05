import { memo, useEffect, useMemo, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { CalendarDays, ChevronLeft, ChevronRight, AlertCircle } from 'lucide-react'
import { EmptyState } from '@/components/EmptyState'
import { useCalendar, useServerClock } from '@/hooks/useCalendar'
import {
  flagOf, IMPACT_DOT, IMPACT_LABEL, fmtTime, fmtDay, fmtWeekRange, fmtCountdown,
  localWeekStart, localWeekEnd, dayIndexOf as weekDayIndex,
} from '@/lib/calendar'
import type { CalendarEvent, Impact, Surprise } from '@/types'

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

// The nine majors' currencies (mirrors the backend DEFAULT_COUNTRIES). Chips toggle these; none
// selected = all.
const CURRENCIES = ['USD', 'EUR', 'GBP', 'JPY', 'CAD', 'AUD', 'NZD', 'CHF', 'CNY']
const IMPACTS: Impact[] = ['HIGH', 'MEDIUM', 'LOW']

// ── time helpers (all display in the browser's local timezone) ──────────────────

// `localWeekStart` / `localWeekEnd` / `fmtDay` / `fmtWeekRange` / `dayIndexOf` all live in
// `lib/calendar.ts` — the Overview preview reads the same week and links in with the same day
// index, and the `(weekStart, weekEnd)` pair IS the query's cache key, so one definition is what
// keeps the two pages sharing a single fetch instead of issuing two.

function actualCls(s: Surprise | null): string {
  if (s === 'beat') return 'text-pos-text'
  if (s === 'miss') return 'text-neg-text'
  return 'text-text-primary'
}

// ── small pieces ────────────────────────────────────────────────────────────────

function ImpactDot({ impact }: { impact: Impact }) {
  return (
    <span
      className={`inline-block w-[8px] h-[8px] rounded-full flex-shrink-0 ${IMPACT_DOT[impact]}`}
      title={`${IMPACT_LABEL[impact]} impact`}
    />
  )
}

function NowLine({ nowMs, nextHigh }: { nowMs: number; nextHigh: CalendarEvent | null }) {
  return (
    <div data-testid="now-line" className="flex items-center gap-2 py-1.5">
      <span className="text-[10px] font-semibold uppercase tracking-[0.5px] text-accent px-1.5 py-0.5 rounded bg-accent/10 font-mono tabular-nums">
        Now {fmtTime(nowMs)}
      </span>
      <div className="flex-1 h-px bg-accent/40" />
      {nextHigh && (
        <span className="text-[11px] text-text-secondary font-mono tabular-nums">
          <span title={nextHigh.currency}>{flagOf(nextHigh.currency)}</span> {nextHigh.title} in{' '}
          <span className="text-accent font-semibold">{fmtCountdown(nextHigh.timestamp_ms - nowMs)}</span>
        </span>
      )}
    </div>
  )
}

// ⚠ MEMOISED, and the reason is the clock rather than the data. `useServerClock` re-renders this
// page once a second so the countdown stays honest, and a week is ~200 events — so without this
// every row rebuilt every second to render text that changes when a single row crosses `now`.
// Both props are primitives, so the memo holds for every row but that one.
const EventRow = memo(function EventRow({ event, passed }: { event: CalendarEvent; passed: boolean }) {
  return (
    <div data-testid="calendar-row" className={`grid grid-cols-[64px_44px_16px_1fr_90px_90px_90px] items-center gap-2 py-2 px-3 border-b border-border-subtle/40 text-sm ${passed ? 'opacity-55' : ''}`}>
      <span className="font-mono tabular-nums text-text-secondary text-xs">{fmtTime(event.timestamp_ms)}</span>
      <span className="text-base leading-none" title={event.currency}>{flagOf(event.currency)}</span>
      <ImpactDot impact={event.impact} />
      <span className="truncate text-text-primary" title={event.category ? `${event.title} · ${event.category}` : event.title}>
        {event.title}
      </span>
      <span className={`font-mono tabular-nums text-xs text-right ${actualCls(event.surprise)}`}>{event.actual ?? '—'}</span>
      <span className="font-mono tabular-nums text-xs text-right text-text-secondary">{event.forecast ?? '—'}</span>
      <span className="font-mono tabular-nums text-xs text-right text-text-tertiary">{event.previous ?? '—'}</span>
    </div>
  )
})

// ── page ────────────────────────────────────────────────────────────────────────

export function Calendar() {
  const [sp, setSp] = useSearchParams()
  const weekOffset = parseInt(sp.get('week') ?? '0', 10) || 0
  const dayParam = sp.get('day')
  // ⚠ Range-checked, not just parsed. `?day=abc` gave NaN, which matches no event, so the page
  // rendered "No events" with every filter looking untouched — a hand-typed or truncated URL
  // reading as an empty week.
  const parsedDay = dayParam === null ? null : parseInt(dayParam, 10)
  const selectedDay =
    parsedDay === null || !Number.isInteger(parsedDay) || parsedDay < 0 || parsedDay > 6
      ? null
      : parsedDay
  const selectedCurrencies = (sp.get('cur') ?? '').split(',').filter(Boolean)
  const impRaw = sp.get('imp') // null = all, '' = none, else CSV of levels
  const enabledImpacts = new Set<Impact>(
    impRaw === null ? IMPACTS : (impRaw.split(',').filter(Boolean) as Impact[]),
  )
  const impactAll = enabledImpacts.size === IMPACTS.length // default → also lets NONE-impact rows show
  const category = sp.get('cat') ?? ''

  // ⚠ Recomputed EVERY RENDER, never memoized on `[weekOffset]`. A value derived from the CLOCK
  // cannot be cached on a key that does not contain the clock: `weekOffset` does not change at
  // midnight, so a tab left open across Sunday→Monday went on asking for LAST week for ever, with
  // the day-strip dates and the Today highlight stale to match. The Overview fixed exactly this on
  // 2026-08-05 and its comment claimed this page already recomputed — it did not. The 1s
  // `useServerClock` tick is what carries the value over the boundary with no reload.
  const fromMs = localWeekStart(weekOffset)
  const toMs = localWeekEnd(fromMs)

  const { data, isLoading, isError, isPlaceholderData, dataUpdatedAt } = useCalendar(fromMs, toMs)

  // Server-clock offset drives the "now" line + countdown, not the (possibly wrong) browser clock.
  const nowMs = useServerClock(data?.server_now_ms)

  // ⚠ `placeholderData` keeps the PREVIOUS week's payload on screen while a new week loads, and
  // the previous week is simply the wrong answer to the question now on screen. Rendering it gave
  // the pill "Aug 10 – 16" over an all-zero day strip (counts are computed against the new
  // `fromMs`) and a list of the week before. Held data is only honest when the key is unchanged.
  const loadingWeek = isLoading || isPlaceholderData
  const allEvents = loadingWeek ? [] : (data?.events ?? [])
  // TanStack keeps `data` through a failed background refetch. Discarding a good week over one
  // failed poll is worse than showing it — so a failure with data on hand is a dated BANNER, and
  // only a failure with nothing to show takes the page.
  const staleAfterError = isError && !!data && !loadingWeek
  const fatalError = isError && !data

  const dayIndexOf = (ts: number) => weekDayIndex(ts, fromMs)

  const passFilters = (e: CalendarEvent) =>
    (selectedCurrencies.length === 0 || selectedCurrencies.includes(e.currency)) &&
    (impactAll || enabledImpacts.has(e.impact)) &&
    (category === '' || e.category === category)

  // Everything matching the currency/impact/category filters (but NOT the day selection) — drives
  // the day-strip counts so the strip stays consistent with the list.
  const filtered = useMemo(() => allEvents.filter(passFilters), [allEvents, sp])
  const dayCounts = useMemo(() => {
    const counts = new Array(7).fill(0)
    for (const e of filtered) {
      const i = dayIndexOf(e.timestamp_ms)
      if (i >= 0 && i < 7) counts[i] += 1
    }
    return counts
  }, [filtered, fromMs])

  // The visible list additionally honours the selected day.
  const visible = useMemo(
    () => (selectedDay === null ? filtered : filtered.filter((e) => dayIndexOf(e.timestamp_ms) === selectedDay)),
    [filtered, selectedDay, fromMs],
  )

  // ⚠ The "now" line belongs to the week that CONTAINS now. It used to render on every week, so
  // paging to next week put `Now 14:32` above its first event and paging back put it under the
  // last — a marker for a moment nowhere on screen. Derived from the clock, not from `weekOffset`,
  // so it survives the midnight rollover with everything else.
  const isCurrentWeek = nowMs >= fromMs && nowMs < toMs
  const nowIdx = isCurrentWeek ? visible.findIndex((e) => e.timestamp_ms > nowMs) : -2 // -2 = don't draw
  const nextHigh = isCurrentWeek
    ? visible.find((e) => e.timestamp_ms > nowMs && e.impact === 'HIGH') ?? null
    : null

  const groups = useMemo(() => {
    const byDay = new Map<number, CalendarEvent[]>()
    for (const e of visible) {
      const i = dayIndexOf(e.timestamp_ms)
      const list = byDay.get(i)
      if (list) list.push(e)
      else byDay.set(i, [e])
    }
    return Array.from(byDay.values())
  }, [visible, fromMs])

  // Category dropdown options come from the whole week (stable regardless of the other filters).
  const categories = useMemo(
    () => Array.from(new Set(allEvents.map((e) => e.category).filter(Boolean))).sort() as string[],
    [allEvents],
  )
  // ⚠ A category is a property of the LOADED WEEK, and the selection lives in the URL, so paging to
  // a week with no `Labor` rows left the `<select>` matching no option — it rendered BLANK over an
  // empty list, which reads as the page breaking rather than as a filter still being applied. The
  // selection is kept (paging back must restore it) and the empty state names it instead.
  const categoryMissing = category !== '' && !loadingWeek && allEvents.length > 0 && !categories.includes(category)

  const todayWeekdayIdx = (new Date().getDay() + 6) % 7 // 0 = Mon — today's weekday, any week
  const todayIdx = weekOffset === 0 ? todayWeekdayIdx : -1

  // ── URL setters ──
  const patch = (kv: Record<string, string | null>) => {
    const next = new URLSearchParams(sp)
    for (const [k, v] of Object.entries(kv)) {
      if (v === null) next.delete(k)
      else next.set(k, v)
    }
    setSp(next, { replace: true })
  }
  const toggleCurrency = (c: string) => {
    const set = new Set(selectedCurrencies)
    set.has(c) ? set.delete(c) : set.add(c)
    patch({ cur: set.size ? Array.from(set).join(',') : null })
  }
  const toggleImpact = (lvl: Impact) => {
    const set = new Set(enabledImpacts)
    set.has(lvl) ? set.delete(lvl) : set.add(lvl)
    patch({ imp: set.size === IMPACTS.length ? null : Array.from(set).join(',') })
  }
  const selectDay = (i: number) => patch({ day: selectedDay === i ? null : String(i) })
  const goToday = () => patch({ week: null, day: String(todayWeekdayIdx) })

  // Open on today: on first mount, if we're on the current week with no explicit day, select today.
  // Runs once — deselecting today (→ whole week) afterwards sticks.
  const didDefaultDay = useRef(false)
  useEffect(() => {
    if (didDefaultDay.current) return
    didDefaultDay.current = true
    if (weekOffset === 0 && sp.get('day') === null) patch({ day: String(todayWeekdayIdx) })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  let flatIdx = -1

  return (
    <div>
      {/* ── Title + week nav ── */}
      <div className="flex items-center flex-wrap gap-3 mb-4">
        <h1 className="text-h1 font-semibold">Economic Calendar</h1>
        <div className="flex items-center gap-1">
          <button onClick={() => patch({ week: String(weekOffset - 1), day: null })}
            className="p-1.5 rounded text-text-secondary hover:bg-bg-hover hover:text-text-primary transition-colors" title="Previous week">
            <ChevronLeft size={16} />
          </button>
          <span className="text-sm font-mono tabular-nums text-text-primary min-w-[130px] text-center">{fmtWeekRange(fromMs)}</span>
          <button onClick={() => patch({ week: String(weekOffset + 1), day: null })}
            className="p-1.5 rounded text-text-secondary hover:bg-bg-hover hover:text-text-primary transition-colors" title="Next week">
            <ChevronRight size={16} />
          </button>
          {(weekOffset !== 0 || selectedDay !== todayIdx) && (
            <button onClick={goToday}
              className="ml-1 text-[11px] px-2 py-1 rounded border border-border-default text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors">
              Today
            </button>
          )}
        </div>
        <span className="text-sm text-text-tertiary">Live macro releases · actual vs forecast vs previous</span>
      </div>

      {/* ── Day summary strip ── */}
      <div className="grid grid-cols-7 gap-2 mb-4">
        {WEEKDAYS.map((wd, i) => {
          const date = new Date(fromMs)
          date.setDate(date.getDate() + i)
          const isSel = selectedDay === i
          const isToday = todayIdx === i
          return (
            <button
              key={i}
              onClick={() => selectDay(i)}
              className={`text-left rounded-lg border px-3 py-2 transition-colors ${
                isSel
                  ? 'border-accent/50 bg-accent/10'
                  : 'border-border-subtle bg-bg-surface hover:bg-bg-hover'
              }`}
            >
              <div className="flex items-baseline justify-between">
                <span className={`text-xs font-semibold ${isToday ? 'text-accent' : 'text-text-secondary'}`}>{wd}</span>
                <span className={`text-sm font-mono tabular-nums ${isToday ? 'text-accent' : 'text-text-primary'}`}>{date.getDate()}</span>
              </div>
              <div className="mt-1 flex items-center justify-between text-[11px]">
                <span className="text-text-tertiary">Economic</span>
                {/* An em-dash while the week loads, never `0`. The counts are computed against the
                    NEW week's `fromMs`, so with the previous week's events still held they were
                    all genuinely zero — a strip confidently reporting an empty week. */}
                <span data-testid="day-count" className="font-mono tabular-nums text-text-secondary">
                  {loadingWeek ? '—' : dayCounts[i]}
                </span>
              </div>
            </button>
          )
        })}
      </div>

      {/* ── Filters ── */}
      <div className="flex items-center flex-wrap gap-3 mb-4">
        {/* Impact — independent toggles (High/Medium/Low), default all on */}
        <div className="flex items-center gap-1">
          {IMPACTS.map((lvl) => {
            const on = enabledImpacts.has(lvl)
            return (
              <button key={lvl} onClick={() => toggleImpact(lvl)}
                className={`flex items-center gap-1.5 text-[11px] px-2 py-1 rounded border transition-colors ${
                  on ? 'border-accent/40 bg-accent/10 text-text-primary' : 'border-border-default text-text-tertiary hover:bg-bg-hover'
                }`}>
                <span className={`inline-block w-[7px] h-[7px] rounded-full ${on ? IMPACT_DOT[lvl] : 'bg-text-tertiary/40'}`} />
                {IMPACT_LABEL[lvl]}
              </button>
            )
          })}
        </div>

        <div className="w-px h-5 bg-border-subtle" />

        {/* Category dropdown */}
        <select
          value={category}
          onChange={(e) => patch({ cat: e.target.value || null })}
          className="text-[12px] bg-bg-surface border border-border-default rounded px-2 py-1 text-text-secondary hover:text-text-primary focus:outline-none focus:border-accent/50 cursor-pointer"
        >
          <option value="">All categories</option>
          {/* The held selection is offered even when this week has no such row, or the `<select>`
              would match no option and render blank while still filtering. */}
          {categoryMissing && <option value={category}>{category}</option>}
          {categories.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>

        <div className="w-px h-5 bg-border-subtle" />

        {/* Currency chips */}
        <div className="flex items-center flex-wrap gap-1">
          {CURRENCIES.map((c) => {
            const on = selectedCurrencies.includes(c)
            return (
              <button key={c} onClick={() => toggleCurrency(c)} title={c}
                className={`flex items-center gap-1 text-[11px] font-mono px-1.5 py-1 rounded border transition-colors ${
                  on ? 'border-accent/40 bg-accent/10 text-accent' : 'border-border-default text-text-tertiary hover:text-text-secondary hover:bg-bg-hover'
                }`}>
                <span className="text-sm leading-none">{flagOf(c)}</span>
                {c}
              </button>
            )
          })}
          {selectedCurrencies.length > 0 && (
            <button onClick={() => patch({ cur: null })} className="ml-1 text-[11px] text-text-tertiary hover:text-text-secondary underline">clear</button>
          )}
        </div>
      </div>

      {/* ── List ──
          Order matters: a week still loading must never fall through to "No events", and a failed
          refetch that still has a good week must never take the list away. */}
      {loadingWeek && (
        <div className="p-6 text-text-secondary text-sm">Loading {fmtWeekRange(fromMs)}…</div>
      )}

      {fatalError && (
        <EmptyState icon={<AlertCircle size={22} />} title="Couldn't load the calendar"
          description="The TradingView feed didn't respond. It will retry automatically on the next poll." />
      )}

      {/* A failed poll over a week already on screen. The rows stay — they were true — and the
          banner DATES them, so nothing on this page is left looking live when it is not. */}
      {staleAfterError && (
        <div className="flex items-center gap-2 mb-3 px-3 py-2 rounded-md border border-warn-text/30 bg-warn-muted text-[12px] text-warn-text">
          <AlertCircle size={13} className="flex-shrink-0" />
          <span>
            The feed didn't answer the last refresh — showing the calendar as of{' '}
            <span className="font-mono tabular-nums">{fmtTime(dataUpdatedAt)}</span>. Retrying automatically.
          </span>
        </div>
      )}

      {!loadingWeek && !fatalError && visible.length === 0 && (
        categoryMissing ? (
          <EmptyState icon={<CalendarDays size={22} />} title={`No “${category}” events this week`}
            description="That category is still selected but nothing in this week is filed under it. Pick another category, or switch back to all." />
        ) : (
          <EmptyState icon={<CalendarDays size={22} />} title="No events"
            description="Nothing matches the current filters. Widen the impact, category, currency or day selection." />
        )
      )}

      {!loadingWeek && !fatalError && visible.length > 0 && (
        <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
          <div className="grid grid-cols-[64px_44px_16px_1fr_90px_90px_90px] gap-2 py-2 px-3 border-b border-border-subtle text-[10px] uppercase tracking-[0.5px] text-text-tertiary font-semibold">
            <span>Time</span><span>Cur</span><span /><span>Event</span>
            <span className="text-right">Actual</span><span className="text-right">Forecast</span><span className="text-right">Previous</span>
          </div>

          {groups.map((dayEvents) => (
            <div key={dayIndexOf(dayEvents[0].timestamp_ms)}>
              <div className="px-3 py-1.5 bg-bg-sunken/60 border-b border-border-subtle/60 text-xs font-semibold text-text-secondary">
                {fmtDay(dayEvents[0].timestamp_ms)}
              </div>
              {dayEvents.map((e) => {
                flatIdx += 1
                const showNow = flatIdx === nowIdx
                return (
                  // ⚠ The position is part of the key. `(time, currency, title)` is NOT unique in
                  // real data — the live feed carries e.g. two `CAD Budget Balance` rows at one
                  // timestamp — and duplicate keys are how React silently drops or mis-reuses a row.
                  <div key={`${e.timestamp_ms}|${e.currency}|${e.title}|${flatIdx}`}>
                    {showNow && <div className="px-3"><NowLine nowMs={nowMs} nextHigh={nextHigh} /></div>}
                    <EventRow event={e} passed={e.timestamp_ms <= nowMs} />
                  </div>
                )
              })}
            </div>
          ))}

          {nowIdx === -1 && <div className="px-3"><NowLine nowMs={nowMs} nextHigh={null} /></div>}
        </div>
      )}
    </div>
  )
}
