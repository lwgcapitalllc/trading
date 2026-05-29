import { useNavigate } from 'react-router-dom'
import { useSystemHealth } from '@/hooks/useLab'
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
      { key: 'api',     label: 'API',     state: 'grey', tip: 'checking…' },
      { key: 'ssh',     label: 'SSH',     state: 'grey', tip: 'checking…' },
      { key: 'agent',   label: 'Agent',   state: 'grey', tip: 'checking…' },
      { key: 'nt8',     label: 'NT8',     state: 'grey', tip: 'checking…' },
      { key: 'compile', label: 'Compile', state: 'grey', tip: 'checking…' },
    ]
  }

  const nt8State: DotState = !h.nt8_running
    ? 'red'
    : !h.nt8_sa_visible
    ? 'yellow'
    : 'green'

  const nt8Tip = !h.nt8_running
    ? 'NT8: not running'
    : !h.nt8_sa_visible
    ? 'NT8: running — no Strategy Analyzer window'
    : 'NT8: running + Strategy Analyzer open'

  return [
    {
      key: 'api',
      label: 'API',
      state: h.backend ? 'green' : 'red',
      tip: h.backend ? 'Backend: healthy' : 'Backend: unreachable',
    },
    {
      key: 'ssh',
      label: 'SSH',
      state: h.ssh_tunnel ? 'green' : 'red',
      tip: h.ssh_tunnel ? 'SSH: connected' : 'SSH: unreachable',
    },
    {
      key: 'agent',
      label: 'Agent',
      state: h.vps_agent ? 'green' : 'red',
      tip: h.vps_agent ? 'VPS agent: ok' : 'VPS agent: unreachable',
    },
    {
      key: 'nt8',
      label: 'NT8',
      state: nt8State,
      tip: nt8Tip,
    },
    {
      key: 'compile',
      label: 'CC',
      state: h.last_compile_ok ? 'green' : 'red',
      tip: h.last_compile_ok
        ? 'Compile: clean'
        : `Compile: ${h.last_compile_errors.length} error${h.last_compile_errors.length !== 1 ? 's' : ''}`,
    },
  ]
}

// ── Dot visual ────────────────────────────────────────────────────────────────

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

function Dot({ def, onRedClick }: { def: DotDef; onRedClick: () => void }) {
  return (
    <div className="flex flex-col items-center gap-[5px]">
      <span
        title={def.tip}
        onClick={def.state === 'red' ? onRedClick : undefined}
        className={`w-[7px] h-[7px] rounded-full flex-shrink-0 transition-colors duration-300 ${DOT_CLS[def.state]} ${def.state === 'red' ? 'cursor-pointer' : ''}`}
        style={DOT_GLOW[def.state] ? { boxShadow: DOT_GLOW[def.state] } : undefined}
      />
      <span className="text-[9px] text-text-tertiary leading-none select-none">{def.label}</span>
    </div>
  )
}

// ── Strip ─────────────────────────────────────────────────────────────────────

export function SystemHealthStrip() {
  const navigate = useNavigate()
  const { data: health } = useSystemHealth()
  const dots = buildDots(health)

  return (
    <div className="flex items-start justify-between px-1 pb-1">
      {dots.map(def => (
        <Dot
          key={def.key}
          def={def}
          onRedClick={() => navigate('/settings')}
        />
      ))}
    </div>
  )
}
