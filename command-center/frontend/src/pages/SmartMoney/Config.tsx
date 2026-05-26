import { useState, useEffect, useCallback } from 'react'
import { GitBranch, Check, AlertTriangle, RotateCcw } from 'lucide-react'
import type { SmartMoneyConfig as ConfigType, ConfigGitStatus } from '@/types'

interface ConfigProps {
  config: ConfigType
  gitStatus: ConfigGitStatus | undefined
  onSave: (c: ConfigType) => void
  isSaving: boolean
  saveError: string | null
}

function NumberField({ label, description, value, onChange, min = 0 }: {
  label: string
  description?: string
  value: number
  onChange: (v: number) => void
  min?: number
}) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-border-subtle last:border-0">
      <div className="cfg-field-label">
        <div className="text-small text-text-secondary">{label}</div>
        {description && <div className="text-[10px] text-text-tertiary">{description}</div>}
      </div>
      <input
        type="number"
        min={min}
        className="bg-bg-base border border-border-default rounded-md px-[9px] py-[5px] text-small text-text-primary font-mono text-right w-[78px] focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent-muted"
        value={value}
        onChange={e => onChange(Number(e.target.value))}
      />
    </div>
  )
}

const WEIGHT_KEYS: Array<{ key: keyof ConfigType; label: string }> = [
  { key: 'weight_winrate_consistency',  label: 'Win-rate consistency' },
  { key: 'weight_risk_adjusted_return', label: 'Risk-adjusted return' },
  { key: 'weight_exit_efficiency',      label: 'Exit efficiency' },
  { key: 'weight_trade_frequency',      label: 'Trade frequency' },
  { key: 'weight_instrument_consistency', label: 'Instrument & day consistency' },
]

export function Config({ config, gitStatus, onSave, isSaving, saveError }: ConfigProps) {
  const [form, setForm] = useState<ConfigType>(config)
  const [savedForm] = useState<ConfigType>(config)

  useEffect(() => { setForm(config) }, [config])

  const set = useCallback(<K extends keyof ConfigType>(key: K, value: ConfigType[K]) => {
    setForm(prev => ({ ...prev, [key]: value }))
  }, [])

  const weightSum = WEIGHT_KEYS.reduce((s, { key }) => s + (form[key] as number), 0)
  const weightsOk = Math.abs(weightSum - 100) < 0.01
  const lookbackOk = form.lookback_min_days <= form.lookback_preferred_days &&
                     form.lookback_preferred_days <= form.lookback_elite_days

  const canSave = weightsOk && lookbackOk && !isSaving

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        {/* Qualification thresholds */}
        <div className="bg-bg-surface border border-border-subtle rounded-lg p-4">
          <div className="text-micro font-semibold uppercase tracking-[0.7px] text-text-secondary mb-3 flex items-center gap-[7px]">
            <Check size={12} />
            Qualification thresholds
          </div>
          <NumberField label="Minimum trades" value={form.min_trades} onChange={v => set('min_trades', v)} min={1} />
          <NumberField label="Minimum win rate" description="per 30-day window (%)" value={form.min_win_rate_pct} onChange={v => set('min_win_rate_pct', v)} />
          <NumberField label="Max peak drawdown %" value={form.max_drawdown_pct} onChange={v => set('max_drawdown_pct', v)} />
          <NumberField label="Min active weeks / month" value={form.min_active_weeks_per_month} onChange={v => set('min_active_weeks_per_month', v)} min={1} />
          <NumberField label="Max single-trade PnL share %" value={form.max_single_trade_pnl_share_pct} onChange={v => set('max_single_trade_pnl_share_pct', v)} />
          <NumberField label="Max avg hold time" description="hours" value={form.max_avg_hold_hours} onChange={v => set('max_avg_hold_hours', v)} />
          <NumberField label="Min account age" description="days" value={form.min_account_age_days} onChange={v => set('min_account_age_days', v)} min={1} />
        </div>

        <div className="space-y-3">
          {/* Lookback tiers */}
          <div className="bg-bg-surface border border-border-subtle rounded-lg p-4">
            <div className="text-micro font-semibold uppercase tracking-[0.7px] text-text-secondary mb-3 flex items-center gap-[7px]">
              <svg className="w-[12px] h-[12px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
              Lookback tiers
              <small className="normal-case tracking-normal text-text-tertiary font-normal ml-auto">days · must be ordered</small>
            </div>
            {!lookbackOk && (
              <div className="text-micro text-warn-text bg-warn-muted rounded px-2 py-1 mb-2">
                Lookback tiers must be ordered: min ≤ preferred ≤ elite
              </div>
            )}
            <NumberField label="Minimum qualification" value={form.lookback_min_days} onChange={v => set('lookback_min_days', v)} min={1} />
            <NumberField label="Preferred" value={form.lookback_preferred_days} onChange={v => set('lookback_preferred_days', v)} min={1} />
            <NumberField label="Elite designation" value={form.lookback_elite_days} onChange={v => set('lookback_elite_days', v)} min={1} />
          </div>

          {/* Strike rules */}
          <div className="bg-bg-surface border border-border-subtle rounded-lg p-4">
            <div className="text-micro font-semibold uppercase tracking-[0.7px] text-text-secondary mb-3 flex items-center gap-[7px]">
              <AlertTriangle size={12} />
              Strike rules
              <small className="normal-case tracking-normal text-text-tertiary font-normal ml-auto">months</small>
            </div>
            <NumberField label="Below threshold → yellow flag" value={form.strike_months_to_yellow} onChange={v => set('strike_months_to_yellow', v)} min={1} />
            <NumberField label="Consecutive below → disqualify" value={form.strike_months_to_disqualify} onChange={v => set('strike_months_to_disqualify', v)} min={1} />
            <NumberField label="Consecutive above → reinstate" value={form.strike_months_to_reinstate} onChange={v => set('strike_months_to_reinstate', v)} min={1} />
          </div>
        </div>
      </div>

      {/* Scoring weights */}
      <div className="bg-bg-surface border border-border-subtle rounded-lg p-4">
        <div className="text-micro font-semibold uppercase tracking-[0.7px] text-text-secondary mb-3 flex items-center gap-[7px]">
          <svg className="w-[12px] h-[12px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 3v18h18"/><path d="m7 14 4-4 3 3 5-5"/></svg>
          Scoring weights
          <small className="normal-case tracking-normal text-text-tertiary font-normal ml-auto">must sum to 100</small>
        </div>
        <div className="space-y-[9px]">
          {WEIGHT_KEYS.map(({ key, label }) => {
            const val = form[key] as number
            return (
              <div key={key} className="py-[9px] border-b border-border-subtle last:border-0">
                <div className="flex justify-between text-small mb-[6px]">
                  <span className="text-text-secondary">{label}</span>
                  <b className="font-mono font-semibold text-accent-text">{val.toFixed(0)}%</b>
                </div>
                <input
                  type="range" min={0} max={50} step={1} value={val}
                  onChange={e => set(key, Number(e.target.value))}
                  className="w-full h-[5px] rounded-pill bg-bg-surface-2 appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-[15px] [&::-webkit-slider-thumb]:h-[15px] [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-accent [&::-webkit-slider-thumb]:cursor-pointer"
                />
              </div>
            )
          })}
        </div>

        {/* Weight sum indicator */}
        <div className={`flex items-center gap-[9px] mt-3 px-3 py-[9px] rounded-md text-small ${weightsOk ? 'bg-pos-muted text-pos-text' : 'bg-neg-muted text-neg-text'}`}>
          {weightsOk
            ? <Check size={14} />
            : <AlertTriangle size={14} />}
          <span>{weightsOk ? 'Weights sum correctly' : 'Weights must sum to 100 — adjust before saving'}</span>
          <span className="font-mono font-semibold ml-auto">{weightSum.toFixed(0)}</span>
        </div>
      </div>

      {/* Action bar */}
      <div className="flex items-center gap-[9px] pt-[14px] border-t border-border-subtle">
        {gitStatus && (
          <div className={`flex items-center gap-[7px] text-micro px-[11px] py-[5px] rounded-pill ${gitStatus.is_dirty ? 'bg-warn-muted text-warn-text' : 'bg-pos-muted text-pos-text'}`}>
            <GitBranch size={12} />
            {gitStatus.is_dirty ? 'Uncommitted changes' : 'Clean — committed'}
          </div>
        )}
        {gitStatus?.last_commit_message && (
          <span className="text-micro text-text-tertiary">
            last commit · "{gitStatus.last_commit_message}" · {gitStatus.last_commit_at ? new Date(gitStatus.last_commit_at).toLocaleDateString() : ''}
          </span>
        )}

        <div className="ml-auto flex gap-[9px]">
          <button
            onClick={() => setForm(savedForm)}
            className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small border border-border-default bg-bg-surface text-text-primary hover:bg-bg-hover hover:border-border-strong transition-colors duration-[120ms]"
          >
            <RotateCcw size={12} />
            Reset to last saved
          </button>
          <button
            onClick={() => setForm(config)}
            className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small border border-border-default bg-bg-surface text-text-primary hover:bg-bg-hover hover:border-border-strong transition-colors duration-[120ms]"
          >
            <RotateCcw size={12} />
            Reset to last committed
          </button>
          <button
            disabled={!canSave}
            onClick={() => canSave && onSave(form)}
            className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small font-medium bg-accent border border-accent text-[#06201d] hover:bg-accent-hover transition-colors duration-[120ms] disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Save config
          </button>
        </div>
      </div>

      {saveError && (
        <div className="text-micro text-neg-text bg-neg-muted border border-neg-muted px-3 py-2 rounded-md">
          Save failed: {saveError}
        </div>
      )}

      <div className="text-micro text-text-tertiary bg-bg-sunken border border-border-subtle rounded-md px-3 py-[10px] flex gap-2 items-start">
        <svg className="w-[14px] h-[14px] flex-shrink-0 mt-[1px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>
        <span><b className="text-text-secondary">Save writes the pipeline config file locally only — it does not commit or push.</b> The pipeline reads this exact file, so the UI and pipeline never disagree. Committing is a separate, deliberate step with a real message. Weights must sum to 100 before save is allowed.</span>
      </div>
    </div>
  )
}
