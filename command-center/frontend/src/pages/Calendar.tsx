import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { CalendarDays, ChevronLeft, ChevronRight, AlertCircle } from 'lucide-react'
import { EmptyState } from '@/components/EmptyState'
import { useCalendar } from '@/hooks/useCalendar'
import type { CalendarEvent, Impact, Surprise } from '@/types'

const DAY_MS = 86_400_000
const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

// The nine majors' currencies (mirrors the backend DEFAULT_COUNTRIES). Chips toggle these; none
// selected = all.
const CURRENCIES = ['USD', 'EUR', 'GBP', 'JPY', 'CAD', 'AUD', 'NZD', 'CHF', 'CNY']
const IMPACTS: Impact[] = ['HIGH', 'MEDIUM', 'LOW']

// Country flag per currency (regional-indicator emoji). Shown instead of the ISO code.
const CURRENCY_FLAG: Record<string, string> = {
  USD: '🇺🇸', EUR: '🇪🇺', GBP: '🇬🇧', JPY: '🇯🇵', CAD: '🇨🇦',
  AUD: '🇦🇺', NZD: '🇳🇿', CHF: '🇨🇭', CNY: '🇨🇳',
}
const flagOf = (currency: string) => CURRENCY_FLAG[currency] ?? currency

const IMPACT_DOT: Record<Impact, string> = {
  HIGH: 'bg-neg-text',
  MEDIUM: 'bg-warn-text',
  LOW: 'bg-text-tertiary',
  NONE: 'bg-text-tertiary/50',
}
const IMPACT_LABEL: Record<Impact, string> = {
  HIGH: 'High',
  MEDIUM: 'Medium',
  LOW: 'Low',
  NONE: 'None',
}

// ── time helpers (all display in the browser's local timezone) ──────────────────

function localWeekStart(offset: number): number {
  const d = new Date()
  const mondayIdx = (d.getDay() + 6) % 7 // 0 = Monday
  d.setHours(0, 0, 0, 0)
  d.setDate(d.getDate() - mondayIdx + offset * 7)
  return d.getTime()
}

const fmtTime = (ms: number) =>
  new Date(ms).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

const fmtDay = (ms: number) =>
  new Date(ms).toLocaleDateString([], { weekday: 'long', month: 'short', day: 'numeric' })

const fmtWeekRange = (fromMs: number) => {
  const opts: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric' }
  const end = new Date(fromMs)
  end.setDate(end.getDate() + 6)
  return `${new Date(fromMs).toLocaleDateString([], opts)} – ${end.toLocaleDateString([], opts)}`
}

function fmtCountdown(deltaMs: number): string {
  const s = Math.max(0, Math.floor(deltaMs / 1000))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${s % 60}s`
  return `${s}s`
}

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
    <div className="flex items-center gap-2 py-1.5">
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

function EventRow({ event, passed }: { event: CalendarEvent; passed: boolean }) {
  return (
    <div className={`grid grid-cols-[64px_44px_16px_1fr_90px_90px_90px] items-center gap-2 py-2 px-3 border-b border-border-subtle/40 text-sm ${passed ? 'opacity-55' : ''}`}>
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
}

// ── page ────────────────────────────────────────────────────────────────────────

export function Calendar() {
  const [sp, setSp] = useSearchParams()
  const weekOffset = parseInt(sp.get('week') ?? '0', 10) || 0
  const dayParam = sp.get('day')
  const selectedDay = dayParam === null ? null : parseInt(dayParam, 10)
  const selectedCurrencies = (sp.get('cur') ?? '').split(',').filter(Boolean)
  const impRaw = sp.get('imp') // null = all, '' = none, else CSV of levels
  const enabledImpacts = new Set<Impact>(
    impRaw === null ? IMPACTS : (impRaw.split(',').filter(Boolean) as Impact[]),
  )
  const impactAll = enabledImpacts.size === IMPACTS.length // default → also lets NONE-impact rows show
  const category = sp.get('cat') ?? ''

  const fromMs = useMemo(() => localWeekStart(weekOffset), [weekOffset])
  const toMs = fromMs + 7 * DAY_MS

  const { data, isLoading, isError } = useCalendar(fromMs, toMs)

  // Server-clock offset drives the "now" line + countdown, not the (possibly wrong) browser clock.
  const offsetRef = useRef(0)
  const [nowMs, setNowMs] = useState(() => Date.now())
  useEffect(() => {
    if (data?.server_now_ms) offsetRef.current = data.server_now_ms - Date.now()
  }, [data?.server_now_ms])
  useEffect(() => {
    const id = setInterval(() => setNowMs(Date.now() + offsetRef.current), 1000)
    return () => clearInterval(id)
  }, [])

  const allEvents = data?.events ?? []

  // Which day (0=Mon … 6=Sun) an event falls on, in local time (round absorbs DST hour drift).
  const dayIndexOf = (ts: number) => {
    const d = new Date(ts)
    d.setHours(0, 0, 0, 0)
    return Math.round((d.getTime() - fromMs) / DAY_MS)
  }

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

  const nowIdx = visible.findIndex((e) => e.timestamp_ms > nowMs) // -1 = all shown events passed
  const nextHigh = visible.find((e) => e.timestamp_ms > nowMs && e.impact === 'HIGH') ?? null

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

  const todayIdx = weekOffset === 0 ? dayIndexOf(nowMs) : -1

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
  const goToday = () => patch({ week: null, day: null })

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
          {(weekOffset !== 0 || selectedDay !== null) && (
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
                <span className="font-mono tabular-nums text-text-secondary">{dayCounts[i]}</span>
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

      {/* ── List ── */}
      {isLoading && <div className="p-6 text-text-secondary text-sm">Loading calendar…</div>}

      {isError && (
        <EmptyState icon={<AlertCircle size={22} />} title="Couldn't load the calendar"
          description="The TradingView feed didn't respond. It will retry automatically on the next poll." />
      )}

      {!isLoading && !isError && visible.length === 0 && (
        <EmptyState icon={<CalendarDays size={22} />} title="No events"
          description="Nothing matches the current filters. Widen the impact, category, currency or day selection." />
      )}

      {!isLoading && !isError && visible.length > 0 && (
        <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
          <div className="grid grid-cols-[64px_44px_16px_1fr_90px_90px_90px] gap-2 py-2 px-3 border-b border-border-subtle text-[10px] uppercase tracking-[0.5px] text-text-tertiary font-semibold">
            <span>Time</span><span>Cur</span><span /><span>Event</span>
            <span className="text-right">Actual</span><span className="text-right">Forecast</span><span className="text-right">Previous</span>
          </div>

          {groups.map((dayEvents, gi) => (
            <div key={gi}>
              <div className="px-3 py-1.5 bg-bg-sunken/60 border-b border-border-subtle/60 text-xs font-semibold text-text-secondary">
                {fmtDay(dayEvents[0].timestamp_ms)}
              </div>
              {dayEvents.map((e) => {
                flatIdx += 1
                const showNow = flatIdx === nowIdx
                return (
                  <div key={e.timestamp_ms + e.currency + e.title}>
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
