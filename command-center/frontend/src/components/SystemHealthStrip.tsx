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
      { key: 'api', label: 'API', state: 'grey', tip: 'checking…' },
      { key: 'ssh', label: 'SSH', state: 'grey', tip: 'checking…' },
      { key: 'nt8', label: 'NT8', state: 'grey', tip: 'checking…' },
      { key: 'mt5', label: 'MT5 Agent', state: 'grey', tip: 'checking…' },
    ]
  }

  // NT8: three-state — agent down → red; agent up but SA not ready → yellow; fully ready → green
  //
  // ⚠ `nt8_running` / `nt8_sa_visible` are `boolean | null` and every check is
  // `=== false`, never falsy — the same rule `mt5_connected` follows below.
  // BOTH come off the agent's own /nt-health, so when the agent is down they are
  // `null` (UNASKED), and a falsy check would render "NinjaTrader not running"
  // for a NinjaTrader nobody asked about. That was exactly wrong on 2026-08-06:
  // the agent was wedged, NT8 was open on the VPS, and the health payload said
  // `nt8_running: false`. The agent-down branch answers first anyway, so this is
  // about the TOOLTIP telling the truth rather than the dot's colour.
  const nt8State: DotState = !h.nt8_agent
    ? 'red'
    : h.nt8_running === false
      ? 'yellow'
      : h.nt8_sa_visible === false
        ? 'yellow'
        : 'green'

  const nt8Tip = !h.nt8_agent
    ? h.ssh_tunnel
      ? 'NT8: agent not running — click to start (NinjaTrader’s own state is unknown until it answers)'
      : 'NT8: agent not running — SSH must be up first'
    : h.nt8_running === false
      ? 'NT8: agent OK — NinjaTrader not running on VPS (open NT8 via RDP)'
      : h.nt8_sa_visible === false
        ? 'NT8: agent OK, NinjaTrader running — Strategy Analyzer not open (open it in NT8)'
        : 'NT8: agent OK, NinjaTrader running, Strategy Analyzer open'

  // SSH: three-state, because "the tunnel is down" and "the VPS is unreachable"
  // are different problems with different fixes and this dot used to conflate
  // them. `ssh_tunnel` now measures the PORT FORWARDS; `vps_reachable` is the
  // separate question of whether the box answers at all. Yellow = the tunnel is
  // down but the VPS is fine, which the supervisor repairs by itself within a
  // minute — so yellow means "wait", not "go and do something".
  const sshState: DotState = h.ssh_tunnel ? 'green' : h.vps_reachable ? 'yellow' : 'red'
  const sshTip = h.ssh_tunnel
    ? 'SSH tunnel: both port forwards up (8765 + 8766)'
    : h.vps_reachable
      ? 'SSH tunnel: down, but the VPS is reachable — the supervisor is rebuilding it'
      : 'SSH: VPS unreachable — check ForexVPS or ssh config'

  // MT5: three-state for the same reason NT8 is. A responding agent is not a
  // usable terminal — every python backtest that needs uncached bars goes
  // through MT5_Lab, so an agent up with the terminal disconnected is a run
  // that will fail at fetch time. `null` = we could not ask, which is reported
  // as such rather than guessed either way.
  const mt5State: DotState = !h.mt5_agent ? 'red' : h.mt5_connected === false ? 'yellow' : 'green'

  const mt5Tip = !h.mt5_agent
    ? h.ssh_tunnel
      ? 'MT5 agent: down — click to start'
      : 'MT5 agent: down — the tunnel must be up first'
    : h.mt5_connected === false
      ? 'MT5 agent OK — the MT5_Lab terminal is NOT connected to the broker (open it via RDP). Bar fetches will fail.'
      : h.mt5_connected === null
        ? 'MT5 agent: responding — terminal state unknown'
        : `MT5 agent OK, terminal connected${h.mt5_server ? ` · ${h.mt5_server}` : ''}${h.mt5_account ? ` · ${h.mt5_account}` : ''}`

  return [
    {
      key: 'api',
      label: 'API',
      state: h.backend ? 'green' : 'red',
      tip: h.backend
        ? 'Local backend: healthy'
        : 'Local backend: unreachable — restart the backend',
    },
    {
      key: 'ssh',
      label: 'SSH',
      state: sshState,
      tip: sshTip,
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
      state: mt5State,
      tip: mt5Tip,
    },
  ]
}

// ── Visuals ───────────────────────────────────────────────────────────────────

const DOT_CLS: Record<DotState, string> = {
  green: 'bg-pos',
  yellow: 'bg-warn-text',
  red: 'bg-neg',
  grey: 'bg-text-tertiary opacity-40',
}

const DOT_GLOW: Record<DotState, string | undefined> = {
  green: '0 0 5px #00ff7f',
  yellow: '0 0 5px #ffb300',
  red: undefined,
  grey: undefined,
}

const STATUS_TEXT: Record<DotState, string> = {
  green: 'ok',
  yellow: 'warn',
  red: 'down',
  grey: '…',
}

const STATUS_TEXT_CLS: Record<DotState, string> = {
  green: 'text-pos-text',
  yellow: 'text-warn-text',
  red: 'text-neg-text',
  grey: 'text-text-tertiary',
}

// ── Row ───────────────────────────────────────────────────────────────────────

function DotRow({
  def,
  onRedClick,
  loading,
}: {
  def: DotDef
  onRedClick: () => void
  loading?: boolean
}) {
  return (
    <div className="flex items-center gap-[8px] py-[3px]" title={def.tip}>
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
        {dots.map((def) => (
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
      {dots.map((def) => (
        <DotRow
          key={def.key}
          def={def}
          onRedClick={() => handleRedClick(def.key)}
          loading={
            (def.key === 'nt8' && startNt8Agent.isPending) ||
            (def.key === 'mt5' && startMt5Agent.isPending)
          }
        />
      ))}
    </div>
  )
}
