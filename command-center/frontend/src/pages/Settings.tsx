import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Save, Settings as SettingsIcon } from 'lucide-react'
import { api } from '@/api/client'
import type { AppSettings } from '@/types'

function Field({
  label,
  description,
  value,
  onChange,
}: {
  label: string
  description?: string
  value: string
  onChange: (v: string) => void
}) {
  return (
    <div className="flex items-start justify-between py-2 border-b border-border-subtle last:border-0">
      <div>
        <div className="text-small text-text-secondary">{label}</div>
        {description && <div className="text-micro text-text-tertiary">{description}</div>}
      </div>
      <input
        className="bg-bg-base border border-border-default rounded-md px-[9px] py-[5px] text-small text-text-primary font-mono w-[340px] focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent-muted"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  )
}

export function Settings() {
  const qc = useQueryClient()
  const { data, isLoading, error } = useQuery({
    queryKey: ['settings'],
    queryFn: () => api.get<AppSettings>('/settings'),
  })

  const [form, setForm] = useState<AppSettings | null>(null)
  useEffect(() => {
    if (data) setForm(data)
  }, [data])

  const {
    mutate: save,
    isPending: saving,
    isSuccess,
  } = useMutation({
    mutationFn: (s: AppSettings) => api.put<AppSettings>('/settings', s),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings'] }),
  })

  const set = (key: keyof AppSettings) => (v: string) =>
    setForm((prev) => (prev ? { ...prev, [key]: v } : prev))

  if (isLoading) return <div className="text-text-tertiary text-small p-6">Loading settings…</div>
  if (error || !form)
    return (
      <div>
        <h1 className="text-h1 font-semibold mb-4">Settings</h1>
        <div className="text-neg-text text-small">Could not load settings: {String(error)}</div>
      </div>
    )

  return (
    <div>
      <div className="flex items-end gap-3 mb-[18px]">
        <h1 className="text-h1 font-semibold">Settings</h1>
        <span className="text-[12px] text-text-tertiary pb-[2px]">
          machine-specific paths · backend config
        </span>
        <div className="ml-auto">
          <button
            onClick={() => save(form)}
            disabled={saving}
            className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small font-medium bg-accent border border-accent text-[#06201d] hover:bg-accent-hover transition-colors duration-[120ms] disabled:opacity-40"
          >
            <Save size={14} />
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>

      {isSuccess && (
        <div className="mb-4 text-micro text-pos-text bg-pos-muted border border-pos-muted px-3 py-2 rounded-md">
          Settings saved.
        </div>
      )}

      <div className="bg-bg-surface border border-border-subtle rounded-lg p-4">
        <div className="text-micro font-semibold uppercase tracking-[0.7px] text-text-secondary mb-3 flex items-center gap-[7px]">
          <SettingsIcon size={12} />
          Machine Paths
        </div>
        <Field label="Monorepo root" value={form.monorepo_root} onChange={set('monorepo_root')} />
        <Field
          label="Smart money root"
          value={form.smart_money_root}
          onChange={set('smart_money_root')}
        />
        <Field
          label="Smart money config path"
          description="The pipeline's config.json"
          value={form.smart_money_config_path}
          onChange={set('smart_money_config_path')}
        />
        <Field
          label="Smart money reports dir"
          value={form.smart_money_reports_dir}
          onChange={set('smart_money_reports_dir')}
        />
        <Field
          label="Bot instances dir"
          value={form.instances_dir}
          onChange={set('instances_dir')}
        />
        <Field
          label="SSH alias"
          description="Used for all VPS connections"
          value={form.ssh_alias}
          onChange={set('ssh_alias')}
        />
        <Field
          label="NT8 agent tunnel"
          description="HTTP tunnel to nt8_agent.py"
          value={form.nt8_agent_tunnel}
          onChange={set('nt8_agent_tunnel')}
        />
        <Field
          label="MT5 agent tunnel"
          description="HTTP tunnel to mt5_agent.py"
          value={form.mt5_agent_tunnel}
          onChange={set('mt5_agent_tunnel')}
        />
      </div>

      <div className="mt-4 text-micro text-text-tertiary bg-bg-sunken border border-border-subtle rounded-md px-3 py-[10px]">
        Edit this one file to update all machine-specific paths. Nothing else hardcodes paths.
      </div>
    </div>
  )
}
