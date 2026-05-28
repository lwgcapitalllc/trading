import { useState, useEffect } from 'react'
import { useBotSnapshot, useSaveBotCaps } from '@/hooks/useBots'
import type { BotStatus } from '@/types'

type BotCapForm = {
  daily_goal: string
  daily_cap: string
  weekly_cap: string
}

function capStr(n: number | null | undefined): string {
  return n != null ? String(n) : ''
}

function isDirty(form: BotCapForm, bot: BotStatus): boolean {
  return (
    form.daily_goal !== capStr(bot.daily_goal_pct) ||
    form.daily_cap  !== capStr(bot.daily_cap_pct)  ||
    form.weekly_cap !== capStr(bot.weekly_cap_pct)
  )
}

function StatusPill({ status }: { status: string }) {
  const isRunning = status === 'RUNNING'
  const cls = isRunning ? 'bg-pos-muted text-pos-text' : 'bg-neg-muted text-neg-text'
  return (
    <span className={`inline-flex text-[10px] font-semibold px-2 py-[3px] rounded-pill uppercase tracking-[0.4px] ${cls}`}>
      {isRunning ? 'Running' : 'Stopped'}
    </span>
  )
}

function SectionLabel({ title }: { title: string }) {
  return (
    <p className="text-[9px] font-semibold uppercase tracking-[0.8px] text-text-tertiary mt-[14px] mb-[4px]">
      {title}
    </p>
  )
}

function PerfRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-[4px]">
      <span className="text-[11px] text-text-tertiary">{label}</span>
      <span className="text-[11px] font-mono">{children}</span>
    </div>
  )
}

function ConfigRow({
  label, value, onChange,
}: {
  label: string
  value: string
  onChange: (val: string) => void
}) {
  return (
    <div className="flex items-center justify-between py-[4px]">
      <span className="text-[11px] text-text-secondary">{label}</span>
      <div className="flex items-center gap-[4px]">
        <input
          type="number"
          value={value}
          step={0.5}
          min={0}
          onChange={e => onChange(e.target.value)}
          className="w-[64px] bg-bg-sunken border border-border-subtle rounded px-[7px] py-[3px] text-[11px] font-mono text-right focus:border-accent/50 outline-none transition-colors"
        />
        <span className="text-[10px] text-text-tertiary w-[12px]">%</span>
      </div>
    </div>
  )
}

function PnlValue({ usd, pct }: { usd: number | null; pct: number | null }) {
  if (usd == null || pct == null) return <span className="text-text-tertiary">—</span>
  const sign = usd >= 0 ? '+' : ''
  const cls  = pct > 0 ? 'text-pos-text' : pct < 0 ? 'text-neg-text' : 'text-text-tertiary'
  return (
    <span className={cls}>
      {sign}${Math.abs(usd).toFixed(2)} ({sign}{pct.toFixed(2)}%)
    </span>
  )
}

function formatUptime(seconds: number | null): string {
  if (seconds == null) return '—'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return `${h}h ${m}m`
}

export function ConfigureTab() {
  const { data: snapshot } = useBotSnapshot()
  const saveCaps = useSaveBotCaps()
  const [forms, setForms] = useState<Record<string, BotCapForm>>({})

  useEffect(() => {
    if (!snapshot) return
    setForms(prev => {
      const next = { ...prev }
      for (const bot of snapshot.bots) {
        if (!next[bot.name]) {
          next[bot.name] = {
            daily_goal: capStr(bot.daily_goal_pct),
            daily_cap:  capStr(bot.daily_cap_pct),
            weekly_cap: capStr(bot.weekly_cap_pct),
          }
        }
      }
      return next
    })
  }, [snapshot])

  if (!snapshot) return null

  function updateField(botName: string, field: keyof BotCapForm, val: string) {
    setForms(prev => ({
      ...prev,
      [botName]: { ...(prev[botName] ?? {}), [field]: val },
    }))
  }

  function handleSave(bot: BotStatus) {
    const form = forms[bot.name]
    if (!form) return
    saveCaps.mutate(
      {
        botName: bot.name,
        caps: {
          daily_goal_pct: parseFloat(form.daily_goal),
          daily_cap_pct:  parseFloat(form.daily_cap),
          weekly_cap_pct: parseFloat(form.weekly_cap),
        },
      },
      {
        onSuccess: () => {
          setForms(prev => { const n = { ...prev }; delete n[bot.name]; return n })
        },
      },
    )
  }

  return (
    <div>
      <div className="grid grid-cols-4 gap-4">
        {snapshot.bots.map((bot: BotStatus) => {
          const form = forms[bot.name]
          if (!form) return null
          const dirty    = isDirty(form, bot)
          const isSaving = saveCaps.isPending && saveCaps.variables?.botName === bot.name

          return (
            <div key={bot.name} className="bg-bg-surface border border-border-subtle rounded-lg p-4 flex flex-col">

              {/* Header */}
              <div className="flex items-center justify-between mb-2">
                <span className="text-[13px] font-semibold">{bot.name}</span>
                <StatusPill status={bot.status} />
              </div>

              {/* Performance */}
              <SectionLabel title="Performance" />
              <PerfRow label="Daily P&L">
                <PnlValue usd={bot.daily_pnl} pct={bot.daily_pnl_pct} />
              </PerfRow>
              <PerfRow label="Weekly P&L">
                <PnlValue usd={bot.weekly_pnl} pct={bot.weekly_pnl_pct} />
              </PerfRow>
              <PerfRow label="Trades today">
                <span className={bot.trades_today != null ? 'text-text-secondary' : 'text-text-tertiary'}>
                  {bot.trades_today != null ? String(bot.trades_today) : '—'}
                </span>
              </PerfRow>
              <PerfRow label="Uptime">
                <span className="text-text-secondary">{formatUptime(bot.uptime_seconds)}</span>
              </PerfRow>

              {/* Risk caps */}
              <SectionLabel title="Risk Caps" />
              <ConfigRow
                label="Daily goal"
                value={form.daily_goal}
                onChange={v => updateField(bot.name, 'daily_goal', v)}
              />
              <ConfigRow
                label="Daily cap"
                value={form.daily_cap}
                onChange={v => updateField(bot.name, 'daily_cap', v)}
              />
              <ConfigRow
                label="Weekly cap"
                value={form.weekly_cap}
                onChange={v => updateField(bot.name, 'weekly_cap', v)}
              />

              {/* Save button */}
              <div className="mt-auto pt-4">
                <button
                  disabled={!dirty || isSaving}
                  onClick={() => handleSave(bot)}
                  className={`w-full px-3 py-[7px] rounded-md text-small font-medium transition-colors ${
                    dirty && !isSaving
                      ? 'bg-accent-muted text-accent-text border border-accent/30 hover:bg-accent/10 cursor-pointer'
                      : 'bg-bg-surface-2 text-text-tertiary border border-border-subtle cursor-not-allowed opacity-50'
                  }`}
                >
                  {isSaving ? 'Saving…' : 'Save config'}
                </button>
              </div>

            </div>
          )
        })}
      </div>

      <p className="text-[10px] text-text-tertiary mt-4">
        Risk cap changes are saved locally and reflected in this dashboard immediately. The running bot on the VPS uses the hardcoded thresholds until you push a code change — these overrides are for monitoring reference only.
      </p>
    </div>
  )
}
