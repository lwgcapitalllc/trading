import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard, Radar, Bot, BarChart2,
  Activity, Settings,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { SystemHealthStrip } from '@/components/SystemHealthStrip'

const WORKSPACE: { to: string; label: string; icon: LucideIcon; live: boolean }[] = [
  { to: '/',            label: 'Overview',    icon: LayoutDashboard, live: true  },
  { to: '/smart-money', label: 'Smart Money', icon: Radar,           live: true  },
  { to: '/bots',        label: 'Bots',        icon: Bot,             live: true  },
]

const RESEARCH: { to: string; label: string; icon: LucideIcon; live: boolean }[] = [
  { to: '/backtests',    label: 'Backtests',    icon: BarChart2, live: true  },
  { to: '/stress-tests', label: 'Stress Tests', icon: Activity,  live: true  },
]

function NavItem({ to, label, icon: Icon, live }: { to: string; label: string; icon: LucideIcon; live: boolean }) {
  return (
    <NavLink
      to={to}
      end={to === '/'}
      className={({ isActive }) =>
        'flex items-center gap-[10px] px-[9px] py-2 rounded-md text-[13px] cursor-pointer select-none relative transition-colors duration-[120ms] ' +
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
          <Icon
            size={16}
            className={`flex-shrink-0 transition-all duration-[120ms] ${
              isActive
                ? 'text-accent drop-shadow-glow-accent'
                : 'opacity-85'
            }`}
          />
          {label}
          {!live && (
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
  return (
    <aside className="w-[212px] flex-shrink-0 bg-bg-sunken border-r border-border-subtle flex flex-col">

      {/* ── Logo ──────────────────────────────────────────────────── */}
      <div className="flex items-center justify-center px-4 py-5 border-b border-border-subtle">
        <NavLink to="/">
          <img
            src="/logo.png"
            alt="LWG Capital"
            className="w-full max-w-[148px] h-auto select-none cursor-pointer"
            draggable={false}
          />
        </NavLink>
      </div>

      {/* ── Nav ───────────────────────────────────────────────────── */}
      <div className="flex flex-col flex-1 py-[14px] px-3">

      {/* ── Workspace items (no section label) ───────────────────── */}
      {WORKSPACE.map(item => <NavItem key={item.to} {...item} />)}

      {/* ── Research section ──────────────────────────────────────── */}
      <div className="text-[10px] uppercase tracking-[1px] text-text-tertiary px-2 pt-[14px] pb-[6px] font-semibold">
        Research
      </div>
      {RESEARCH.map(item => <NavItem key={item.to} {...item} />)}

      {/* ── Footer ────────────────────────────────────────────────── */}
      <div className="mt-auto pt-[10px] border-t border-border-subtle">
        <SystemHealthStrip />

        {/* Settings — last item */}
        <NavLink
          to="/settings"
          className={({ isActive }) =>
            'flex items-center gap-[10px] px-[9px] py-[7px] mt-[8px] rounded-md text-[13px] cursor-pointer select-none relative transition-colors duration-[120ms] ' +
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
              Settings
            </>
          )}
        </NavLink>
      </div>
      </div>
    </aside>
  )
}
