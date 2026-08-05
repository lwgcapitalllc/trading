import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import {
  LayoutDashboard, Radar, Bot, CalendarDays, BookOpen, ClipboardList, BarChart2, Sliders,
  Activity, Settings, ChevronsLeft, ChevronsRight, RefreshCw,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { SystemHealthStrip } from '@/components/SystemHealthStrip'
import { useBacktestRuns, useOptimizations } from '@/hooks/useLab'
import { useStressTests } from '@/hooks/useStressTests'
import { FEATURES } from '@/lib/features'
import type { FeatureKey } from '@/lib/features'

// `feature` ties a row to a flag in lib/features.ts. A row whose flag is off is
// not rendered here AND has no route in App.tsx — the two must move together, or
// a hidden page is still reachable by typing its URL.
type NavEntry = { to: string; label: string; icon: LucideIcon; live: boolean; feature?: FeatureKey }

// Grouped by what each item IS, not by page type. Order inside "Lab" follows the
// actual strategy-development lifecycle (write → backtest → optimize → stress test),
// so the list reads top-to-bottom as the workflow. Overview sits above all sections,
// ungrouped, as the dashboard.
const SECTIONS: { label?: string; items: NavEntry[] }[] = [
  {
    items: [
      { to: '/',            label: 'Overview',    icon: LayoutDashboard, live: true },
    ],
  },
  {
    label: 'Lab',
    items: [
      { to: '/strategies',    label: 'Strategies',    icon: BookOpen,   live: true },
      { to: '/backtests',     label: 'Backtests',     icon: BarChart2,  live: true },
      { to: '/optimizations', label: 'Optimizations', icon: Sliders,    live: true },
      { to: '/stress-tests',  label: 'Stress Tests',  icon: Activity,   live: true },
    ],
  },
  {
    label: 'Live',
    items: [
      { to: '/bots',        label: 'Bots',        icon: Bot,   live: true },
      { to: '/smart-money', label: 'Smart Money', icon: Radar, live: true, feature: 'smartMoney' },
    ],
  },
  {
    label: 'Reference',
    items: [
      { to: '/rulesets', label: 'Rulesets', icon: ClipboardList, live: true },
      { to: '/calendar', label: 'Calendar', icon: CalendarDays,  live: true },
    ],
  },
]

// A row behind an OFF flag is dropped, and a section left with nothing goes with
// it — a section header over no rows is a heading for nothing.
const VISIBLE_SECTIONS = SECTIONS
  .map(section => ({ ...section, items: section.items.filter(i => !i.feature || FEATURES[i.feature]) }))
  .filter(section => section.items.length > 0)

// Pulsing dot meaning "a job is running under this item". Anchored to the icon's top-right
// corner so it reads identically whether the sidebar is expanded or collapsed.
function ActivityDot() {
  return (
    <span className="absolute -top-[3px] -right-[3px] flex h-[7px] w-[7px]" aria-label="active">
      <span className="absolute inline-flex h-full w-full rounded-full bg-accent opacity-60 animate-ping" />
      <span className="relative inline-flex h-[7px] w-[7px] rounded-full bg-accent" />
    </span>
  )
}

// Refresh-everything action. It lives here rather than in the top bar because the
// bar's width now carries the affirmation ribbon — and this is a global action, so
// the global nav is where it belongs. Styled as a footer row so it reads as a peer
// of Settings, and collapses to an icon like every other row.
function RefreshAll({ collapsed }: { collapsed: boolean }) {
  const qc = useQueryClient()
  const [refreshing, setRefreshing] = useState(false)

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await qc.invalidateQueries()
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <button
      onClick={handleRefresh}
      disabled={refreshing}
      title={collapsed ? 'Refresh all data' : undefined}
      className={
        'w-full flex items-center gap-[10px] px-[9px] py-[7px] mt-[8px] rounded-md text-[13px] ' +
        'cursor-pointer select-none transition-colors duration-[120ms] ' +
        'text-text-tertiary hover:bg-bg-hover hover:text-text-secondary ' +
        (collapsed ? 'justify-center ' : '')
      }
    >
      <RefreshCw size={16} className={`flex-shrink-0 opacity-85 ${refreshing ? 'animate-spin' : ''}`} />
      {!collapsed && 'Refresh data'}
    </button>
  )
}

function NavItem({ to, label, icon: Icon, live, collapsed, active = false }: {
  to: string; label: string; icon: LucideIcon; live: boolean; collapsed: boolean; active?: boolean
}) {
  return (
    <NavLink
      to={to}
      end={to === '/'}
      title={collapsed ? (active ? `${label} — running` : label) : undefined}
      className={({ isActive }) =>
        'flex items-center gap-[10px] px-[9px] py-2 rounded-md text-[13px] cursor-pointer select-none relative transition-colors duration-[120ms] ' +
        (collapsed ? 'justify-center ' : '') +
        (isActive
          ? 'bg-accent-muted text-text-primary'
          : live
          ? 'text-text-secondary hover:bg-bg-hover hover:text-text-primary'
          : 'text-text-tertiary hover:bg-bg-hover hover:text-text-secondary')
      }
    >
      {({ isActive }) => (
        <>
          {isActive && (
            <span className="absolute left-[-12px] top-2 bottom-2 w-[3px] bg-accent rounded-r-[3px]" />
          )}
          <span className="relative flex-shrink-0">
            <Icon
              size={16}
              className={`transition-all duration-[120ms] ${
                isActive
                  ? 'text-accent drop-shadow-glow-accent'
                  : 'opacity-85'
              }`}
            />
            {active && <ActivityDot />}
          </span>
          {!collapsed && label}
          {!collapsed && active && (
            <span className="ml-auto text-[9px] font-semibold px-[6px] py-[1px] rounded-pill uppercase tracking-[0.4px] bg-accent-muted text-accent">
              Running
            </span>
          )}
          {!collapsed && !live && (
            <span className="ml-auto text-[9px] font-semibold px-[6px] py-[1px] rounded-pill uppercase tracking-[0.4px] bg-bg-surface-2 text-text-tertiary">
              Soon
            </span>
          )}
        </>
      )}
    </NavLink>
  )
}

export function Sidebar() {
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try { return localStorage.getItem('sidebar_collapsed') === '1' } catch { return false }
  })

  // Running-job indicators, mapped per nav route. Each mirrors the "active" logic of its page:
  // a backtest/sweep run in progress (excluding optimization combos, which belong to Optimizations),
  // an optimization grid running, or any stress-test phase running. Hooks already poll on their own.
  const { data: runs } = useBacktestRuns()
  const { data: optimizations } = useOptimizations()
  const { data: stressTests } = useStressTests()
  const activeByRoute: Record<string, boolean> = {
    '/backtests':     runs?.some(r => r.status === 'running' && !r.optimization_id) ?? false,
    '/optimizations': optimizations?.some(o => o.status === 'running') ?? false,
    '/stress-tests':  stressTests?.some(s => s.status.startsWith('running')) ?? false,
  }
  const toggle = () => setCollapsed(c => {
    const next = !c
    try { localStorage.setItem('sidebar_collapsed', next ? '1' : '0') } catch { /* quota */ }
    return next
  })

  return (
    <aside className={`flex-shrink-0 bg-bg-sunken border-r border-border-subtle flex flex-col transition-[width] duration-200 ${collapsed ? 'w-[64px]' : 'w-[212px]'}`}>

      {/* ── Logo ──────────────────────────────────────────────────── */}
      <div className={`flex items-center justify-center py-5 border-b border-border-subtle ${collapsed ? 'px-2' : 'px-4'}`}>
        <NavLink to="/">
          <img
            src="/logo.png"
            alt="LWG Capital"
            className={`h-auto select-none cursor-pointer ${collapsed ? 'w-[40px]' : 'w-full max-w-[148px]'}`}
            draggable={false}
          />
        </NavLink>
      </div>

      {/* ── Nav ───────────────────────────────────────────────────── */}
      <div className="flex flex-col flex-1 py-[14px] px-3">

      {/* ── Grouped nav sections ──────────────────────────────────── */}
      {VISIBLE_SECTIONS.map((section, i) => (
        <div key={section.label ?? 'top'}>
          {/* Section header: a label when expanded, a thin divider when collapsed.
              The first (Overview) section has no header — it sits flush at the top. */}
          {i > 0 && (
            collapsed ? (
              <div className="my-[12px] mx-1 border-t border-border-subtle/60" />
            ) : (
              <div className="text-[10px] uppercase tracking-[1px] text-text-tertiary px-2 pt-[14px] pb-[6px] font-semibold">
                {section.label}
              </div>
            )
          )}
          {section.items.map(item => (
            <NavItem key={item.to} {...item} collapsed={collapsed} active={activeByRoute[item.to]} />
          ))}
        </div>
      ))}

      {/* ── Footer ────────────────────────────────────────────────── */}
      <div className="mt-auto pt-[10px] border-t border-border-subtle">
        <SystemHealthStrip collapsed={collapsed} />

        {/* Refresh all data — moved out of the top bar 2026-08-03 */}
        <RefreshAll collapsed={collapsed} />

        {/* Settings — last nav item */}
        <NavLink
          to="/settings"
          title={collapsed ? 'Settings' : undefined}
          className={({ isActive }) =>
            'flex items-center gap-[10px] px-[9px] py-[7px] mt-[8px] rounded-md text-[13px] cursor-pointer select-none relative transition-colors duration-[120ms] ' +
            (collapsed ? 'justify-center ' : '') +
            (isActive
              ? 'bg-accent-muted text-text-primary'
              : 'text-text-tertiary hover:bg-bg-hover hover:text-text-secondary')
          }
        >
          {({ isActive }) => (
            <>
              {isActive && (
                <span className="absolute left-[-12px] top-[6px] bottom-[6px] w-[3px] bg-accent rounded-r-[3px]" />
              )}
              <Settings size={16} className="flex-shrink-0 opacity-85" />
              {!collapsed && 'Settings'}
            </>
          )}
        </NavLink>

        {/* Collapse / expand toggle — discrete icon tucked in the corner */}
        <div className={`mt-[6px] flex ${collapsed ? 'justify-center' : 'justify-end'}`}>
          <button
            onClick={toggle}
            title={collapsed ? 'Expand menu' : 'Collapse menu'}
            className="p-1.5 rounded text-text-tertiary/50 hover:text-text-secondary hover:bg-bg-hover transition-colors duration-[120ms]"
          >
            {collapsed ? <ChevronsRight size={15} /> : <ChevronsLeft size={15} />}
          </button>
        </div>
      </div>
      </div>
    </aside>
  )
}
