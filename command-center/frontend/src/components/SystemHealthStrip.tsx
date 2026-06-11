import { useNavigate } from 'react-router-dom'
import { useSystemHealth, useStartNt8Agent, useStartMt5Agent } from '@/hooks/useLab'
import type { SystemHealth } from '@/types'

// ── Dot state ─────────────────────────────────────────────────────────────────

type DotState = 'green' | 'yellow' | 'red' | 'grey'

interface DotDef {
  key: string
  label: string
  state: DotState
  tip: string
}

function buildDots(h: SystemHealth | undefined): DotDef[] {
  if (!h) {
    return [
      { key: 'api',   label: 'API',       state: 'grey', tip: 'checking…' },
      { key: 'ssh',   label: 'SSH',       state: 'grey', tip: 'checking…' },
      { key: 'nt8',   label: 'NT8',       state: 'grey', tip: 'checking…' },
      { key: 'mt5',   label: 'MT5 Agent', state: 'grey', tip: 'checking…' },
    ]
  }

  // NT8: three-state — agent down → red; agent up but SA not ready → yellow; fully ready → green
  const nt8State: DotState = !h.nt8_agent
    ? 'red'
    : !h.nt8_running
    ? 'yellow'
    : !h.nt8_sa_visible
    ? 'yellow'
    : 'green'

  const nt8Tip = !h.nt8_agent
    ? h.ssh_tunnel
      ? 'NT8: agent not running — click to start'
      : 'NT8: agent not running — SSH must be up first'
    : !h.nt8_running
    ? 'NT8: agent OK — NinjaTrader not running on VPS (open NT8 via RDP)'
    : !h.nt8_sa_visible
    ? 'NT8: agent OK, NinjaTrader running — Strategy Analyzer not open (open it in NT8)'
    : 'NT8: agent OK, NinjaTrader running, Strategy Analyzer open'

  return [
    {
      key: 'api',
      label: 'API',
      state: h.backend ? 'green' : 'red',
      tip: h.backend ? 'Local backend: healthy' : 'Local backend: unreachable — restart the backend',
    },
    {
      key: 'ssh',
      label: 'SSH',
      state: h.ssh_tunnel ? 'green' : 'red',
      tip: h.ssh_tunnel ? 'SSH to VPS: connected' : 'SSH to VPS: unreachable — check ForexVPS or ssh config',
    },
    {
      key: 'nt8',
      label: 'NT8',
      state: nt8State,
      tip: nt8Tip,
    },
    {
      key: 'mt5',
      label: 'MT5 Agent',
      state: h.mt5_agent ? 'green' : 'red',
      tip: h.mt5_agent
        ? 'MT5 agent: responding'
        : h.ssh_tunnel
        ? 'MT5 agent: down — click to start'
        : 'MT5 agent: down — SSH must be up first',
    },
  ]
}

// ── Visuals ───────────────────────────────────────────────────────────────────

const DOT_CLS: Record<DotState, string> = {
  green:  'bg-pos',
  yellow: 'bg-warn-text',
  red:    'bg-neg',
  grey:   'bg-text-tertiary opacity-40',
}

const DOT_GLOW: Record<DotState, string | undefined> = {
  green:  '0 0 5px #00ff7f',
  yellow: '0 0 5px #ffb300',
  red:    undefined,
  grey:   undefined,
}

const STATUS_TEXT: Record<DotState, string> = {
  green:  'ok',
  yellow: 'warn',
  red:    'down',
  grey:   '…',
}

const STATUS_TEXT_CLS: Record<DotState, string> = {
  green:  'text-pos-text',
  yellow: 'text-warn-text',
  red:    'text-neg-text',
  grey:   'text-text-tertiary',
}

// ── Row ───────────────────────────────────────────────────────────────────────

function DotRow({ def, onRedClick, loading }: { def: DotDef; onRedClick: () => void; loading?: boolean }) {
  return (
    <div
      className="flex items-center gap-[8px] py-[3px]"
      title={def.tip}
    >
      <span
        className={`w-[6px] h-[6px] rounded-full flex-shrink-0 transition-colors duration-300 ${DOT_CLS[def.state]} ${def.state === 'red' ? 'cursor-pointer' : ''} ${loading ? 'animate-pulse' : ''}`}
        style={DOT_GLOW[def.state] ? { boxShadow: DOT_GLOW[def.state] } : undefined}
        onClick={def.state === 'red' ? onRedClick : undefined}
      />
      <span className="text-[11px] text-text-secondary flex-1 leading-none">{def.label}</span>
      <span className={`text-[10px] font-mono leading-none ${STATUS_TEXT_CLS[def.state]}`}>
        {loading ? '…' : STATUS_TEXT[def.state]}
      </span>
    </div>
  )
}

// ── Strip ─────────────────────────────────────────────────────────────────────

export function SystemHealthStrip({ collapsed }: { collapsed?: boolean }) {
  const navigate = useNavigate()
  const { data: health } = useSystemHealth()
  const startNt8Agent = useStartNt8Agent()
  const startMt5Agent = useStartMt5Agent()
  const dots = buildDots(health)

  function handleRedClick(key: string) {
    if (key === 'nt8' && health?.ssh_tunnel) {
      startNt8Agent.mutate()
    } else if (key === 'mt5' && health?.ssh_tunnel) {
      startMt5Agent.mutate()
    } else {
      navigate('/settings')
    }
  }

  // Collapsed sidebar — dots only, centered, label/status in the tooltip.
  if (collapsed) {
    return (
      <div className="flex flex-col items-center gap-[7px] pb-2">
        {dots.map(def => (
          <span
            key={def.key}
            title={`${def.label}: ${STATUS_TEXT[def.state]}`}
            className={`w-[7px] h-[7px] rounded-full transition-colors duration-300 ${DOT_CLS[def.state]} ${def.state === 'red' ? 'cursor-pointer' : ''}`}
            style={DOT_GLOW[def.state] ? { boxShadow: DOT_GLOW[def.state] } : undefined}
            onClick={def.state === 'red' ? () => handleRedClick(def.key) : undefined}
          />
        ))}
      </div>
    )
  }

  return (
    <div className="px-2 pb-2">
      {dots.map(def => (
        <DotRow
          key={def.key}
          def={def}
          onRedClick={() => handleRedClick(def.key)}
          loading={
            (def.key === 'nt8'   && startNt8Agent.isPending) ||
            (def.key === 'mt5'   && startMt5Agent.isPending)
          }
        />
      ))}
    </div>
  )
}
