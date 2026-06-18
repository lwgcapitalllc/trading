import { useState } from 'react'
import { Pencil, X, Lock, ExternalLink, ClipboardList } from 'lucide-react'
import { useFirms, usePatchPersonalRuleset } from '@/hooks/useLab'
import { EmptyState } from '@/components/EmptyState'
import { RulesetTypeBadge } from '@/components/RulesetTypeBadge'
import { toast } from 'sonner'
import type { Ruleset } from '@/types'

// Firm names for the group headers. The id prefix "lucidflex" is the program name —
// the FIRM is Lucid (Lucid Trading); LucidFlex stays in the row names instead.
const FIRM_BRAND_NAMES: Record<string, string> = {
  lucidflex:  'Lucid',
  tradeify:   'Tradeify',
  fundednext: 'FundedNext',
  apex:       'Apex',
}

function firmBrand(firmId: string): string {
  const prefix = firmId.split('_')[0]
  return FIRM_BRAND_NAMES[prefix] ?? (prefix.charAt(0).toUpperCase() + prefix.slice(1))
}

// ── Contract scaling cell ─────────────────────────────────────────────────────

interface ScalingLadder {
  mode?: string
  bands?: Array<{ profit_min?: number | null; profit_max?: number | null; mini?: number; micro?: number }>
  start?: { mini?: number; micro?: number }
  tiers?: Array<{ profit_trigger?: number; mini?: number; micro?: number }>
  ceiling?: { mini?: number; micro?: number }
}

interface MaxContracts {
  mini_max?: number
  micro_max?: number
  any?: number
  mix_allowed?: boolean
  mix_ratio_micro_per_mini?: number
  scaling?: ScalingLadder | null
}

function ladderLines(s: ScalingLadder): string[] {
  if (s.bands?.length) {
    return s.bands.map(b => {
      const lo = `$${(b.profit_min ?? 0).toLocaleString()}`
      const hi = b.profit_max != null ? `–$${b.profit_max.toLocaleString()}` : '+'
      return `${lo}${hi} profit: ${b.mini}/${b.micro}`
    })
  }
  if (s.tiers?.length) {
    const lines = s.start ? [`start: ${s.start.mini}/${s.start.micro}`] : []
    lines.push(...s.tiers.map(t => `+$${(t.profit_trigger ?? 0).toLocaleString()} profit: ${t.mini}/${t.micro}`))
    return lines
  }
  return []
}

function MixPill({ ratio }: { ratio: number }) {
  return (
    <div className="relative group inline-block">
      <span className="text-[10px] font-bold px-1 py-[1px] rounded bg-accent/10 text-accent border border-accent/20 cursor-default">MIX</span>
      <div className="absolute right-0 top-full mt-1 z-20 hidden group-hover:block bg-bg-sunken border border-border-default rounded-md px-3 py-2 shadow-xl whitespace-nowrap">
        <div className="text-[10px] font-semibold text-text-tertiary uppercase tracking-wide mb-1">Minis + micros share one cap</div>
        <div className="text-[11px] font-mono text-text-secondary">1 mini = {ratio} micros against the limit</div>
        <div className="text-[11px] text-text-tertiary mt-0.5">profit on excess contracts is voided, not a breach</div>
      </div>
    </div>
  )
}

function ContractsCell({ maxContracts }: { maxContracts: Record<string, unknown> | null }) {
  if (!maxContracts) return <span className="text-text-tertiary">—</span>
  const mc = maxContracts as MaxContracts
  const fixedLabel =
    mc.mini_max != null ? `${mc.mini_max} mini / ${mc.micro_max ?? '—'} micro`
    : mc.any != null ? `${mc.any} contracts`
    : null
  if (!fixedLabel) return <span className="text-text-tertiary">—</span>
  if (!mc.scaling) {
    return (
      <span className="flex items-center gap-1.5">
        <span className="font-mono tabular-nums text-text-secondary">{fixedLabel}</span>
        {mc.mix_allowed && <MixPill ratio={mc.mix_ratio_micro_per_mini ?? 10} />}
      </span>
    )
  }
  const lines = ladderLines(mc.scaling)
  const ratchet = mc.scaling.mode === 'cumulative_ratchet'
  return (
    <div className="relative group/scale inline-block">
      <span className="flex items-center gap-1.5">
        <span className="font-mono tabular-nums text-text-secondary">{fixedLabel}</span>
        <span className="text-[10px] font-bold px-1 py-[1px] rounded bg-gold-muted text-gold-text border border-gold-text/20 cursor-default">SCALES</span>
        {mc.mix_allowed && <MixPill ratio={mc.mix_ratio_micro_per_mini ?? 10} />}
      </span>
      {lines.length > 0 && (
        <div className="absolute right-0 top-full mt-1 z-20 hidden group-hover/scale:block bg-bg-sunken border border-border-default rounded-md px-3 py-2 shadow-xl whitespace-nowrap">
          <div className="text-[10px] font-semibold text-text-tertiary uppercase tracking-wide mb-1">
            {ratchet ? 'Scaling ladder — retained once reached' : 'Scaling bands — can move both ways'}
          </div>
          {lines.map((l, i) => <div key={i} className="text-[11px] font-mono text-text-secondary">{l}</div>)}
          {mc.scaling.ceiling && (
            <div className="text-[11px] font-mono text-text-tertiary mt-0.5">
              ceiling: {mc.scaling.ceiling.mini}/{mc.scaling.ceiling.micro}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Personal rules edit modal ─────────────────────────────────────────────────
// Personal/demo rulesets only — the five personal rule fields. Prop rulesets are
// locked server-side (PATCH/PUT return 403); this modal is never offered for them.

function PersonalRulesEditModal({ ruleset, onClose }: { ruleset: Ruleset; onClose: () => void }) {
  const patch = usePatchPersonalRuleset()
  const inputCls = 'bg-bg-sunken border border-border-subtle rounded px-2.5 py-[5px] text-[12px] text-text-primary w-full focus:outline-none focus:border-accent transition-colors'
  const labelCls = 'text-[11px] text-text-secondary block mb-1'

  const [form, setForm] = useState({
    account_size:               String(ruleset.account_size ?? ''),
    daily_loss_cap:             String(ruleset.daily_loss_cap ?? ''),
    daily_profit_target:        String(ruleset.daily_profit_target ?? ''),
    max_drawdown_from_peak_pct: String(ruleset.max_drawdown_from_peak_pct ?? ''),
    max_consecutive_loss_days:  String(ruleset.max_consecutive_loss_days ?? ''),
  })

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm(prev => ({ ...prev, [k]: e.target.value }))

  function handleSave() {
    const body: Record<string, number> = {}
    const fields: Array<[keyof typeof form, string, (v: number) => boolean]> = [
      ['account_size',               'Account size must be a positive number',      v => v > 0],
      ['daily_loss_cap',             'Daily loss cap must be a positive number',    v => v > 0],
      ['daily_profit_target',        'Daily profit target must be a positive number', v => v > 0],
      ['max_drawdown_from_peak_pct', 'Max drawdown % must be between 0 and 100',    v => v > 0 && v <= 100],
      ['max_consecutive_loss_days',  'Max loss days must be at least 1',            v => v >= 1 && Number.isInteger(v)],
    ]
    for (const [key, err, ok] of fields) {
      const raw = form[key]
      if (raw === '') continue                       // unchanged-empty → omit from PATCH
      const v = Number(raw)
      if (!Number.isFinite(v) || !ok(v)) { toast.error(err); return }
      body[key] = v
    }
    if (!Object.keys(body).length) { toast.error('Nothing to save'); return }
    patch.mutate({ rulesetId: ruleset.id, body }, { onSuccess: onClose })
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4" onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="bg-bg-surface border border-border-default rounded-xl w-full max-w-[440px] flex flex-col shadow-2xl">
        <div className="px-5 py-4 border-b border-border-subtle flex items-center justify-between">
          <div>
            <div className="text-[14px] font-semibold">Edit Personal Rules</div>
            <div className="text-[11px] text-text-tertiary font-mono mt-0.5">{ruleset.id}</div>
          </div>
          <button onClick={onClose} className="text-text-tertiary hover:text-text-primary transition-colors"><X size={16} /></button>
        </div>
        <div className="px-5 py-4 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div><label className={labelCls}>Account Size ($)</label><input type="number" step="1000" min="0" className={inputCls} value={form.account_size} onChange={set('account_size')} placeholder="10000" /></div>
            <div><label className={labelCls}>Daily Loss Cap ($)</label><input type="number" step="50" min="0" className={inputCls} value={form.daily_loss_cap} onChange={set('daily_loss_cap')} placeholder="500" /></div>
            <div><label className={labelCls}>Daily Profit Target ($)</label><input type="number" step="50" min="0" className={inputCls} value={form.daily_profit_target} onChange={set('daily_profit_target')} placeholder="1000" /></div>
            <div><label className={labelCls}>Max DD from Peak (%)</label><input type="number" step="0.5" min="0" max="100" className={inputCls} value={form.max_drawdown_from_peak_pct} onChange={set('max_drawdown_from_peak_pct')} placeholder="15" /></div>
            <div><label className={labelCls}>Max Consecutive Loss Days</label><input type="number" step="1" min="1" className={inputCls} value={form.max_consecutive_loss_days} onChange={set('max_consecutive_loss_days')} placeholder="3" /></div>
          </div>
          <p className="text-[11px] text-text-tertiary leading-relaxed">
            A day losing the cap counts toward the consecutive-day fail; hitting the
            profit target halts the day (informational). Drawdown is measured from the
            equity peak. Re-evaluate runs after changing rules — existing verdicts keep
            the values they were graded with.
          </p>
        </div>
        <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-border-subtle">
          <button onClick={onClose} className="px-4 py-[7px] rounded-md text-[13px] text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors">Cancel</button>
          <button onClick={handleSave} disabled={patch.isPending} className="px-4 py-[7px] rounded-md text-[13px] font-medium bg-accent text-bg-base hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed">
            {patch.isPending ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Rulesets view ─────────────────────────────────────────────────────────────

function RulesetsView() {
  const { data: rulesets, isLoading } = useFirms()
  const [brandFilter, setBrandFilter] = useState<string | null>(null)

  if (isLoading) return <FirmsSkeleton />
  if (!rulesets?.length) return (
    <EmptyState
      icon={<ClipboardList size={20} />}
      title="No rulesets configured"
      description="Rulesets are seeded automatically on backend startup."
    />
  )

  const propRulesets = rulesets.filter(r => r.ruleset_type === 'prop_eval' || r.ruleset_type === 'prop_funded')
  const otherRulesets = rulesets.filter(r => r.ruleset_type !== 'prop_eval' && r.ruleset_type !== 'prop_funded')
  const brands = [...new Set(propRulesets.map(r => firmBrand(r.id)))]
  const PERSONAL = 'Personal'
  const visible = brandFilter && brandFilter !== PERSONAL ? [brandFilter] : brands
  const showProp = brandFilter !== PERSONAL && propRulesets.length > 0
  const showPersonal = (brandFilter === null || brandFilter === PERSONAL) && otherRulesets.length > 0
  const filterBtnCls = (active: boolean) =>
    `px-2.5 py-[3px] rounded text-[11px] font-medium transition-colors ${active ? 'bg-accent/15 text-accent' : 'text-text-tertiary hover:text-text-secondary hover:bg-bg-hover'}`

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-end">
        <div className="flex items-center gap-1">
          <button onClick={() => setBrandFilter(null)} className={filterBtnCls(brandFilter === null)}>All</button>
          {brands.map(b => (
            <button key={b} onClick={() => setBrandFilter(brandFilter === b ? null : b)} className={filterBtnCls(brandFilter === b)}>{b}</button>
          ))}
          {otherRulesets.length > 0 && (
            <button onClick={() => setBrandFilter(brandFilter === PERSONAL ? null : PERSONAL)} className={filterBtnCls(brandFilter === PERSONAL)}>{PERSONAL}</button>
          )}
        </div>
      </div>

      {showProp && (
        <div>
          <div className="mb-3">
            <span className="text-[11px] font-semibold text-text-tertiary uppercase tracking-wide">Prop Firm Challenges</span>
          </div>
          <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-border-subtle">
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium">Name</th>
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium">Type</th>
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium">Account Size</th>
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium">Profit Target</th>
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium">Max DD (EOD)</th>
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium">Consistency</th>
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium">Min Days</th>
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium">Contracts</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((brand, bi) => (
                  <>
                    <tr key={`hdr-${brand}`} className={`${bi > 0 ? 'border-t-2 border-border-default' : ''} bg-accent/5 border-l-2 border-l-accent`}>
                      <td colSpan={8} className="px-4 py-2">
                        <span className="text-[12px] font-semibold text-accent uppercase tracking-[0.4px]">{brand}</span>
                      </td>
                    </tr>
                    {propRulesets.filter(r => firmBrand(r.id) === brand).map(r => (
                      <RulesetRow key={r.id} ruleset={r} />
                    ))}
                  </>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {showPersonal && (
        <div>
          <div className="mb-3">
            <span className="text-[11px] font-semibold text-text-tertiary uppercase tracking-wide">Personal &amp; Demo Accounts</span>
          </div>
          <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-border-subtle">
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium">Name</th>
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium">Type</th>
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium">Account Size</th>
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium">Daily Cap</th>
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium">Daily Target</th>
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium">Max DD from Peak</th>
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium">Max Loss Days</th>
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium">Contracts</th>
                </tr>
              </thead>
              <tbody>
                {otherRulesets.map(r => (
                  <RulesetRow key={r.id} ruleset={r} personal />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

function RulesetRow({ ruleset, personal = false }: { ruleset: Ruleset; personal?: boolean }) {
  const [editing, setEditing] = useState(false)
  const editable = ruleset.ruleset_type === 'personal' || ruleset.ruleset_type === 'demo'
  return (
    <>
      {editing && editable && <PersonalRulesEditModal ruleset={ruleset} onClose={() => setEditing(false)} />}
      <tr className="hover:bg-bg-hover transition-colors">
        <td className="px-4 py-3">
          <div className="flex items-center gap-1.5">
            <span className="font-medium">{ruleset.name}</span>
            {ruleset.market === 'forex' && (
              <span className="text-[10px] font-bold px-1 py-[1px] rounded bg-blue-500/12 text-blue-400 border border-blue-500/20">FX</span>
            )}
            {ruleset.docs_url && (
              <a href={ruleset.docs_url} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()} title="View rules documentation" className="text-text-tertiary hover:text-accent transition-colors">
                <ExternalLink size={11} />
              </a>
            )}
            {editable ? (
              <button onClick={e => { e.stopPropagation(); setEditing(true) }} title="Edit personal rules" className="text-text-tertiary hover:text-accent transition-colors ml-0.5">
                <Pencil size={10} />
              </button>
            ) : (
              <span title="Firm rules — not editable" className="text-text-tertiary ml-0.5 cursor-default">
                <Lock size={10} />
              </span>
            )}
          </div>
          <div className="text-[11px] text-text-tertiary font-mono">{ruleset.id}</div>
        </td>
        <td className="px-4 py-3"><RulesetTypeBadge ruleset_type={ruleset.ruleset_type} size="sm" /></td>
        <td className="px-4 py-3 font-mono tabular-nums">${ruleset.account_size.toLocaleString()}</td>
        {!personal ? (
          <>
            <td className="px-4 py-3 font-mono tabular-nums text-pos-text">{ruleset.profit_target > 0 ? `$${ruleset.profit_target.toLocaleString()}` : <span className="text-text-tertiary">—</span>}</td>
            <td className="px-4 py-3 font-mono tabular-nums text-neg-text">${ruleset.max_loss_eod.toLocaleString()}</td>
            <td className="px-4 py-3 text-text-secondary">{ruleset.consistency_pct != null ? `≤ ${ruleset.consistency_pct}%` : <span className="text-text-tertiary">—</span>}</td>
            <td className="px-4 py-3 font-mono tabular-nums text-text-secondary">
              {ruleset.min_trading_days != null
                ? <span title="Minimum trading days to pass the evaluation">{ruleset.min_trading_days}</span>
                : <span className="text-text-tertiary" title="No minimum trading days published for this challenge">—</span>}
            </td>
          </>
        ) : (
          <>
            <td className="px-4 py-3 font-mono tabular-nums text-neg-text">{ruleset.daily_loss_cap != null ? `$${ruleset.daily_loss_cap.toLocaleString()}` : <span className="text-text-tertiary">—</span>}</td>
            <td className="px-4 py-3 font-mono tabular-nums text-pos-text">{ruleset.daily_profit_target != null ? `$${ruleset.daily_profit_target.toLocaleString()}` : <span className="text-text-tertiary">—</span>}</td>
            <td className="px-4 py-3 font-mono tabular-nums text-neg-text">{ruleset.max_drawdown_from_peak_pct != null ? `${ruleset.max_drawdown_from_peak_pct}%` : <span className="text-text-tertiary">—</span>}</td>
            <td className="px-4 py-3 font-mono tabular-nums text-text-secondary">{ruleset.max_consecutive_loss_days != null ? ruleset.max_consecutive_loss_days : <span className="text-text-tertiary">—</span>}</td>
          </>
        )}
        <td className="px-4 py-3"><ContractsCell maxContracts={ruleset.max_contracts} /></td>
      </tr>
    </>
  )
}

function FirmsSkeleton() {
  return (
    <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden animate-pulse">
      {[0, 1, 2, 3].map(i => (
        <div key={i} className="flex gap-4 px-4 py-3 border-b border-border-subtle last:border-0">
          <div className="h-4 w-36 bg-bg-hover rounded" />
          <div className="h-4 w-16 bg-bg-hover rounded" />
          <div className="h-4 w-24 bg-bg-hover rounded" />
          <div className="h-4 w-24 bg-bg-hover rounded" />
        </div>
      ))}
    </div>
  )
}

// ── Page shell ────────────────────────────────────────────────────────────────

export function Rulesets() {
  return (
    <div>
      <div className="flex items-end gap-3 mb-[18px]">
        <h1 className="text-h1 font-semibold">Rulesets</h1>
      </div>
      <RulesetsView />
    </div>
  )
}
