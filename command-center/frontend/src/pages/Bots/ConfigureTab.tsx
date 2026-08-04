import { useState } from 'react'
import { AlertTriangle, ChevronDown, Info, Lock, PackageCheck, Upload } from 'lucide-react'
import {
  useBotSnapshot, useBotParams, useSaveBotRuntime,
  useBotVersion, usePreviewPromote, usePromoteBot,
} from '@/hooks/useBots'
import type { BotParamRow, BotParamsView, BotStatus } from '@/types'

/**
 * What each live bot is actually configured with — and the one lever allowed to move
 * while it runs.
 *
 * This replaced a risk-cap editor whose own footer said the values were "for monitoring
 * reference only": it wrote daily/weekly caps into config fields `algos/live/` does not
 * read. A control that does nothing is worse than no control, because it reads as cover.
 *
 * The editable/read-only split comes from the BACKEND (`services/bot_params.py`) and is
 * never inferred here — `row.editable` is the only thing this file trusts. Strategy
 * parameters are shown in full and locked: changing one means the bot is no longer the
 * bot that was backtested, and the `strategy_source_hash` pin exists to keep that true.
 */

function fmt(v: unknown): string {
  if (v === null || v === undefined || v === '') return '—'
  if (typeof v === 'boolean') return v ? 'On' : 'Off'
  if (typeof v === 'number') return String(v)
  return String(v)
}

function Card({ title, children, right }: {
  title: string; children: React.ReactNode; right?: React.ReactNode
}) {
  return (
    <div className="bg-bg-surface border border-border-subtle rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <p className="text-[9px] font-semibold uppercase tracking-[0.8px] text-gold-text">{title}</p>
        {right}
      </div>
      {children}
    </div>
  )
}

function Row({ label, children, title }: {
  label: string; children: React.ReactNode; title?: string
}) {
  return (
    <div className="flex items-start justify-between gap-3 py-[5px]" title={title}>
      <span className="text-[11px] text-text-tertiary shrink-0">{label}</span>
      <span className="text-[11px] font-mono tabular-nums text-text-secondary text-right break-all">
        {children}
      </span>
    </div>
  )
}

/** Risk % → dollars on the balance the bot last reported. */
function riskUsd(pct: number, balance: number | null): string {
  if (balance == null || !balance) return ''
  return `$${(balance * pct / 100).toLocaleString(undefined, { maximumFractionDigits: 2 })}`
}

// ── which version is deployed, and deploying a new one ──────────────────────────
//
// The card this replaced read `config.json` — the tracked file — and so described what
// SHOULD be deployed rather than what is. Those were the same thing until 2026-08-03, when
// a bot stopped importing from the repo and started running a frozen snapshot. They are now
// routinely different, and the difference is the whole point: you can build version 3 in the
// repo all day and this keeps saying version 2, because version 2 is what is trading.
//
// Everything here comes from the VPS. Nothing is inferred from the local checkout.

function Warn({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-[6px] text-[10px] leading-[1.5] text-amber-400/90
                    bg-amber-400/[0.06] border border-amber-400/20 rounded px-[8px] py-[6px] mt-[8px]">
      <AlertTriangle size={11} className="shrink-0 mt-[1px]" />
      <span>{children}</span>
    </div>
  )
}

function DeployCard({ botName }: { botName: string }) {
  const { data: v, isLoading } = useBotVersion(botName)
  const preview = usePreviewPromote()
  const promote = usePromoteBot()
  const [output, setOutput] = useState<string | null>(null)

  const busy = preview.isPending || promote.isPending

  if (isLoading) return <Card title="Deployed version"><Row label="">loading…</Row></Card>
  if (!v) return <Card title="Deployed version"><Row label="">unavailable</Row></Card>

  // The live process reports a 12-char prefix; compare like for like. A mismatch means a
  // promote landed after the bot started, so the NEW code is on disk and the OLD code is
  // still trading — the most misleading state this page can show, so it is called out.
  const running = v.running_hash && v.hash && !v.hash.startsWith(v.running_hash)
  const behind = v.commits_ahead > 0

  return (
    <Card
      title="Deployed version"
      right={
        <button
          onClick={() => { setOutput(null); preview.mutate({ botName }, {
            onSuccess: r => setOutput(r.output) }) }}
          disabled={busy}
          className="inline-flex items-center gap-[4px] text-[9px] uppercase tracking-[0.4px]
                     text-gold-text hover:text-gold-bright disabled:opacity-40"
        >
          <Upload size={9} /> {busy ? 'working…' : 'promote'}
        </button>
      }
    >
      <Row label="Strategy">{fmt(v.strategy_package)}</Row>
      <Row label="Version">v{fmt(v.strategy_version)}</Row>
      <Row label="Code hash" title={v.hash}>{v.hash ? v.hash.slice(0, 12) : '—'}</Row>
      <Row label="From commit">{fmt(v.commit)}</Row>
      <Row label="Deployed on">{fmt(v.promoted_at)}</Row>
      <Row label="Files">{v.files ? `${v.files} .py` : '—'}</Row>
      <Row label="Repo now">
        {fmt(v.repo_commit)}{behind ? ` · ${v.commits_ahead} ahead` : ' · same'}
      </Row>

      {!v.frozen && (
        <Warn>
          <strong>Not frozen.</strong> This bot still imports from the repo working tree, so a
          pull changes what it trades and can stop it starting. Promote it.
        </Warn>
      )}
      {v.frozen && !v.snapshot_ok && (
        <Warn>
          <strong>Snapshot modified.</strong> The deployed files no longer match their record —
          someone edited them in place, bypassing promote. Re-promote to re-pin.
        </Warn>
      )}
      {running && (
        <Warn>
          <strong>Restart pending.</strong> The running process reports{' '}
          <span className="font-mono">{v.running_hash}</span>, not the deployed hash. The new
          version is on disk but the old one is still trading.
        </Warn>
      )}
      {v.params_drift.length > 0 && (
        <Warn>
          <strong>{v.params_drift.length} setting(s) changed since deploy:</strong>{' '}
          <span className="font-mono">{v.params_drift.join(', ')}</span>. They take effect at
          the next promote, except risk % which applies live.
        </Warn>
      )}

      {output && (
        <div className="mt-[10px] border-t border-border-subtle/60 pt-[8px]">
          <p className="text-[9px] uppercase tracking-[0.4px] text-text-tertiary mb-[6px]">
            Preview — nothing deployed yet
          </p>
          <pre className="text-[10px] leading-[1.45] font-mono text-text-secondary
                          whitespace-pre-wrap break-all max-h-[220px] overflow-y-auto
                          bg-bg-base/60 rounded p-[8px]">{output}</pre>
          <div className="flex items-center gap-[8px] mt-[8px]">
            <button
              onClick={() => promote.mutate({ botName, restart: true }, {
                onSuccess: r => setOutput(r.output) })}
              disabled={busy}
              className="inline-flex items-center gap-[4px] text-[10px] px-[10px] py-[4px]
                         rounded bg-gold-text/15 text-gold-bright hover:bg-gold-text/25
                         disabled:opacity-40"
            >
              <PackageCheck size={11} /> Deploy &amp; restart
            </button>
            <button
              onClick={() => setOutput(null)}
              className="text-[10px] px-[10px] py-[4px] rounded text-text-tertiary
                         hover:text-text-secondary"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      <p className="text-[10px] text-text-tertiary mt-[8px] leading-[1.5] border-t border-border-subtle/60 pt-[8px]">
        This bot runs a frozen copy of its code. Pulling, backtesting or editing the repo does
        not touch it — only promoting does.
      </p>
    </Card>
  )
}

// ── the one editable lever ──────────────────────────────────────────────────────

function RuntimeEditor({ botName, row, balance }: {
  botName: string; row: BotParamRow; balance: number | null
}) {
  const current = Number(row.value)
  const [draft, setDraft] = useState<string>(String(current))
  const [confirming, setConfirming] = useState(false)
  const save = useSaveBotRuntime()

  const next = parseFloat(draft)
  const valid = Number.isFinite(next)
    && (row.min == null || next >= row.min)
    && (row.max == null || next <= row.max)
  const dirty = valid && next !== current

  function commit() {
    save.mutate({ botName, values: { [row.name]: next } },
      { onSuccess: () => setConfirming(false) })
  }

  return (
    <div>
      <div className="flex items-end gap-3">
        <div>
          <p className="text-[10px] text-text-tertiary mb-[3px]">{row.label}</p>
          <div className="flex items-baseline gap-1">
            <span className="text-[22px] font-mono tabular-nums text-text-primary">{fmt(row.value)}</span>
            <span className="text-[11px] text-text-tertiary">{row.unit ?? '%'}</span>
          </div>
          {balance != null && (
            <p className="text-[10px] text-text-tertiary mt-[2px]">
              {riskUsd(current, balance)} per trade at ${balance.toLocaleString()}
            </p>
          )}
        </div>

        <div className="ml-auto flex items-end gap-2">
          <div>
            <p className="text-[10px] text-text-tertiary mb-[3px]">Change to</p>
            <input
              type="number"
              value={draft}
              step={0.5}
              min={row.min ?? undefined}
              max={row.max ?? undefined}
              onChange={e => setDraft(e.target.value)}
              className="w-[78px] bg-bg-sunken border border-border-subtle rounded px-[7px] py-[5px] text-[12px] font-mono text-right focus:border-accent/50 outline-none transition-colors"
            />
          </div>
          <button
            disabled={!dirty || save.isPending}
            onClick={() => setConfirming(true)}
            className={`px-3 py-[6px] rounded-md text-small font-medium transition-colors ${
              dirty && !save.isPending
                ? 'bg-accent-muted text-accent-text border border-accent/30 hover:bg-accent/10 cursor-pointer'
                : 'bg-bg-surface-2 text-text-tertiary border border-border-subtle cursor-not-allowed opacity-50'
            }`}
          >
            {save.isPending ? 'Deploying…' : 'Deploy'}
          </button>
        </div>
      </div>

      {!valid && draft !== '' && (
        <p className="text-[10px] text-neg-text mt-[6px]">
          Must be between {row.min} and {row.max}.
        </p>
      )}

      {row.note && (
        <p className="text-[10px] text-text-tertiary mt-[10px] leading-[1.5] border-t border-border-subtle/60 pt-[8px]">
          <Info size={10} className="inline mr-[4px] -mt-[1px]" />{row.note}
        </p>
      )}

      {confirming && (
        <ConfirmRuntime
          label={row.label}
          from={current}
          to={next}
          unit={row.unit ?? '%'}
          balance={balance}
          pending={save.isPending}
          onCancel={() => setConfirming(false)}
          onConfirm={commit}
        />
      )}
    </div>
  )
}

/**
 * The confirmation carries the NUMBERS, not the question.
 *
 * "Are you sure?" trains you to click yes. A dialog that shows `10% → 5%` and
 * `$200 → $100 per trade` is one you actually read, which is the only thing that makes a
 * confirmation worth having.
 */
function ConfirmRuntime({ label, from, to, unit, balance, pending, onCancel, onConfirm }: {
  label: string; from: number; to: number; unit: string; balance: number | null
  pending: boolean; onCancel: () => void; onConfirm: () => void
}) {
  const bigger = to > from
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onCancel}>
      <div
        className="bg-bg-surface border border-border-default rounded-lg p-5 w-[440px]"
        onClick={e => e.stopPropagation()}
      >
        <p className="text-[13px] font-semibold mb-1">Change {label} on the live bot</p>
        <p className="text-[11px] text-text-tertiary mb-4">
          This commits the instance config, pushes it, and the VPS pulls it.
        </p>

        <div className="bg-bg-sunken border border-border-subtle rounded-md p-3 mb-3">
          <div className="flex items-center justify-center gap-3 font-mono tabular-nums">
            <span className="text-[20px] text-text-tertiary">{from}{unit}</span>
            <span className="text-text-tertiary">→</span>
            <span className={`text-[20px] ${bigger ? 'text-warn-text' : 'text-text-primary'}`}>{to}{unit}</span>
          </div>
          {balance != null && !!balance && (
            <div className="flex items-center justify-center gap-3 mt-[6px] text-[11px] font-mono tabular-nums text-text-tertiary">
              <span>{riskUsd(from, balance)}</span>
              <span>→</span>
              <span className={bigger ? 'text-warn-text' : ''}>{riskUsd(to, balance)}</span>
              <span>per trade</span>
            </div>
          )}
        </div>

        {bigger && (
          <p className="text-[11px] text-warn-text mb-3 flex gap-[6px]">
            <AlertTriangle size={12} className="shrink-0 mt-[1px]" />
            This increases the risk on every future trade.
          </p>
        )}

        <p className="text-[10px] text-text-tertiary mb-4 leading-[1.5]">
          The bot is <strong className="text-text-secondary">not restarted</strong>. It picks the
          change up at the next bar it is flat — no position open and nothing resting — so a resize
          can never land mid-trade.
        </p>

        <div className="flex gap-2 justify-end">
          <button
            onClick={onCancel}
            className="px-3 py-[6px] rounded-md text-small text-text-secondary border border-border-subtle hover:bg-bg-hover cursor-pointer"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={pending}
            className="px-3 py-[6px] rounded-md text-small font-medium bg-accent-muted text-accent-text border border-accent/30 hover:bg-accent/10 cursor-pointer disabled:opacity-50"
          >
            {pending ? 'Deploying…' : 'Deploy change'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── read-only strategy parameters ───────────────────────────────────────────────

function ParamGroup({ group, rows }: { group: string; rows: BotParamRow[] }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="border-b border-border-subtle/60 last:border-b-0">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-2 py-[8px] text-left cursor-pointer"
      >
        <ChevronDown
          size={12}
          className={`text-text-tertiary transition-transform ${open ? '' : '-rotate-90'}`}
        />
        <span className="text-[11px] text-text-secondary">{group}</span>
        <span className="ml-auto text-[10px] text-text-tertiary">{rows.length}</span>
      </button>
      {open && (
        <div className="pb-[8px] pl-[20px]">
          {rows.map(r => (
            <Row key={r.name} label={r.label} title={r.desc ?? undefined}>
              {fmt(r.value)}{r.unit ? ` ${r.unit}` : ''}
            </Row>
          ))}
        </div>
      )}
    </div>
  )
}

function BotPanel({ bot }: { bot: BotStatus }) {
  const { data, isLoading, error } = useBotParams(bot.name)

  if (isLoading) {
    return <div className="text-[11px] text-text-tertiary">Loading {bot.name}…</div>
  }
  if (error || !data) {
    return (
      <div className="text-[11px] text-neg-text">
        Could not read {bot.name}'s configuration: {String(error)}
      </div>
    )
  }

  const v: BotParamsView = data
  const groups = v.strategy.reduce<Record<string, BotParamRow[]>>((acc, r) => {
    (acc[r.group] ??= []).push(r)
    return acc
  }, {})

  // NOTE: `v.version` (from config.json) is deliberately no longer rendered. It states what
  // SHOULD be deployed and goes stale the moment the repo moves; DeployCard reads the VPS.
  const terminal = (v.identity.mt5_path ?? '').split('\\').filter(Boolean)[0] ?? '—'

  return (
    <div className="grid grid-cols-2 gap-4 items-start">

      {/* Risk — the only thing on this page that can be changed */}
      <div className="col-span-2">
        <Card title="Risk per trade">
          {v.runtime.length === 0
            ? <p className="text-[11px] text-text-tertiary">No runtime-editable settings.</p>
            : v.runtime.map(r => (
                <RuntimeEditor key={r.name} botName={bot.name} row={r} balance={bot.balance} />
              ))}
        </Card>
      </div>

      <Card title="Account">
        <Row label="Account">{fmt(v.identity.account)}</Row>
        <Row label="Server">{fmt(v.identity.server)}</Row>
        <Row label="Symbol">{fmt(v.identity.symbol)}</Row>
        <Row label="Timeframe">{fmt(v.identity.timeframe)}</Row>
        <Row label="Terminal" title={v.identity.mt5_path ?? ''}>{terminal}</Row>
        <Row label="Magic">{fmt(v.identity.magic)}</Row>
      </Card>

      <DeployCard botName={bot.name} />

      <div className="col-span-2">
        <Card
          title={`Strategy parameters · ${v.strategy.length}`}
          right={
            <span className="inline-flex items-center gap-[4px] text-[9px] uppercase tracking-[0.4px] text-text-tertiary">
              <Lock size={9} /> read-only
            </span>
          }
        >
          <p className="text-[10px] text-text-tertiary mb-2 leading-[1.5]">
            These decide <strong className="text-text-secondary">which trades</strong> the bot
            takes, so changing one means it is no longer the bot that was backtested. To change
            them: edit in the lab, backtest, then promote — that path re-pins the version hash
            above.
          </p>
          <div>
            {Object.entries(groups).map(([g, rows]) => (
              <ParamGroup key={g} group={g} rows={rows} />
            ))}
          </div>
        </Card>
      </div>
    </div>
  )
}

export function ConfigureTab() {
  const { data: snapshot } = useBotSnapshot()

  if (!snapshot) return null
  if (snapshot.bots.length === 0) {
    return <p className="text-[11px] text-text-tertiary">No bots registered.</p>
  }

  return (
    <div className="space-y-6">
      {snapshot.bots.map(bot => (
        <div key={bot.name}>
          <div className="flex items-center gap-2 mb-2">
            <span className="text-[13px] font-semibold">{bot.name}</span>
            <span className={`inline-flex text-[10px] font-semibold px-2 py-[3px] rounded-pill uppercase tracking-[0.4px] ${
              bot.status === 'RUNNING' ? 'bg-pos-muted text-pos-text' : 'bg-neg-muted text-neg-text'
            }`}>
              {bot.status === 'RUNNING' ? 'Running' : 'Stopped'}
            </span>
          </div>
          <BotPanel bot={bot} />
        </div>
      ))}
    </div>
  )
}
