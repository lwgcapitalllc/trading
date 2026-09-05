/**
 * Start, stop or restart EVERY registered bot at once.
 *
 * 🔴 **These buttons and the per-bot controls were rendered in the same visual language, and they
 * are not the same kind of thing** — one restarts a bot, the other acts on every python process
 * the VPS runs. With one bot registered the distinction is academic; with four it is the click
 * that takes the book down when you meant one row. So the card is DANGER-TINTED, states its scope
 * in its own title, and every button carries the COUNT it will hit. **A label that is a number
 * cannot say one thing while the list says another.**
 *
 * ⚠ **It lives on Overview, not on Bots (Aaron's call, 2026-09-05).** The Bots page is where you
 * manage bots one at a time; this is machinery, and mixing the two is what made every row's ▷ ■ ↻
 * look like these. ⚠ **It is ONE component rather than a copy on each page** — three buttons that
 * stop a live trading fleet are exactly the thing that must not exist twice.
 *
 * ⚠ **The confirmation LISTS the bots by name.** *"Are you sure?"* trains you to click yes; the
 * names of four accounts do not, and a live account is called out because its cost is different
 * in kind rather than degree.
 */
import { useState } from 'react'
import { Play, Square, RotateCcw } from 'lucide-react'
import { useBotSnapshot, useBotStart, useBotStop, useBotRestart } from '@/hooks/useBots'
import type { BotStatus } from '@/types'

type FleetAction = 'start' | 'stop' | 'restart'

function AffectedBots({ bots }: { bots: BotStatus[] }) {
  if (bots.length === 0) return null
  return (
    <div className="mt-3 bg-bg-sunken border border-border-subtle rounded-md p-[10px] max-h-[160px] overflow-y-auto">
      <p className="text-[10px] font-semibold uppercase tracking-[0.6px] text-text-tertiary mb-[6px]">
        Affects {bots.length} {bots.length === 1 ? 'bot' : 'bots'}
      </p>
      {bots.map((b) => (
        <div key={b.key} className="flex items-center gap-[6px] py-[2px]">
          <span
            className={`w-[5px] h-[5px] rounded-full flex-shrink-0 ${
              b.status === 'RUNNING' ? 'bg-pos' : 'bg-neg'
            }`}
          />
          <span className="text-[11px] text-text-secondary truncate">{b.name}</span>
          {b.account_type === 'live' && (
            <span className="ml-auto inline-flex text-[9px] font-semibold px-[5px] py-[1px] rounded-pill uppercase tracking-[0.4px] bg-warn-muted text-warn-text flex-shrink-0">
              live
            </span>
          )}
        </div>
      ))}
    </div>
  )
}

function ConfirmModal({
  label,
  description,
  confirmLabel,
  confirmClass,
  onConfirm,
  onCancel,
  isPending,
}: {
  label: string
  description: React.ReactNode
  confirmLabel: string
  confirmClass: string
  onConfirm: () => void
  onCancel: () => void
  isPending: boolean
}) {
  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-6"
      onClick={onCancel}
    >
      <div
        className="bg-bg-surface border border-border-default rounded-lg w-full max-w-sm p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <p className="text-[14px] font-semibold mb-[6px]">{label}</p>
        <div className="text-[12px] text-text-tertiary mb-5">{description}</div>
        <div className="flex gap-2 justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-[7px] text-small rounded-md border border-border-default bg-bg-surface text-text-secondary hover:bg-bg-hover transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={isPending}
            className={`px-4 py-[7px] text-small rounded-md font-medium transition-colors ${confirmClass} ${isPending ? 'opacity-50 cursor-not-allowed' : ''}`}
          >
            {isPending ? 'Sending…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

export function FleetControls() {
  const { data: snapshot } = useBotSnapshot()
  const [confirm, setConfirm] = useState<FleetAction | null>(null)

  const start = useBotStart()
  const stop = useBotStop()
  const restart = useBotRestart()

  const bots = snapshot?.bots ?? []
  const total = bots.length
  const noBots = total === 0
  const anyRunning = bots.some((b) => b.status === 'RUNNING')
  const anyBusy = start.isPending || stop.isPending || restart.isPending

  if (!snapshot) return null

  return (
    <div className="bg-bg-surface border border-neg/30 rounded-lg p-4">
      <div className="flex items-center mb-[4px]">
        <span className="text-[13px] font-semibold">Fleet controls</span>
        <span className="ml-[8px] inline-flex text-[10px] font-semibold px-2 py-[3px] rounded-pill uppercase tracking-[0.4px] bg-neg-muted text-neg-text">
          all {total} {total === 1 ? 'bot' : 'bots'}
        </span>
        {anyBusy && (
          <span className="ml-auto text-[11px] text-accent animate-pulse">Executing…</span>
        )}
      </div>
      <p className="text-[11px] text-text-tertiary mb-[14px] leading-[1.5]">
        These act on every registered bot at once. To control one bot, open it on the Bots page.
      </p>
      <div className="flex gap-2 flex-wrap">
        <button
          onClick={() => setConfirm('start')}
          disabled={anyBusy || anyRunning || noBots}
          title={
            noBots
              ? 'No bots registered'
              : anyRunning
                ? 'Something is already running — start an individual bot from the Bots page'
                : 'Start every bot via SYS_STARTUP'
          }
          className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small border border-border-default bg-bg-surface text-text-primary hover:bg-bg-hover hover:border-pos/40 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Play size={13} className="text-pos" />
          Start all {total}
        </button>
        <button
          onClick={() => setConfirm('stop')}
          disabled={anyBusy || noBots}
          title={noBots ? 'No bots registered' : `Stop all ${total} bots`}
          className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small border border-neg/40 bg-neg-muted text-neg-text hover:bg-neg/10 hover:border-neg/70 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Square size={13} />
          Stop all {total}
        </button>
        <button
          onClick={() => setConfirm('restart')}
          disabled={anyBusy || noBots}
          title={noBots ? 'No bots registered' : `Restart all ${total} bots`}
          className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small border border-border-default bg-bg-surface text-text-primary hover:bg-bg-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <RotateCcw size={13} />
          Restart all {total}
        </button>
      </div>

      {noBots && (
        <p className="text-[11px] text-warn-text mt-3">
          No bots registered — nothing for these to act on.
        </p>
      )}

      {confirm === 'start' && (
        <ConfirmModal
          label={`Start all ${total} bots?`}
          description={
            <>
              Runs SYS_STARTUP on the VPS, which brings up every registered bot.
              <AffectedBots bots={bots} />
            </>
          }
          confirmLabel={`Start all ${total}`}
          confirmClass="bg-pos-muted text-pos-text border border-pos/40 hover:bg-pos/10"
          onConfirm={() => {
            start.mutate()
            setConfirm(null)
          }}
          onCancel={() => setConfirm(null)}
          isPending={start.isPending}
        />
      )}
      {confirm === 'stop' && (
        <ConfirmModal
          label={`Stop all ${total} bots?`}
          description={
            <>
              Every bot below stops trading and manages nothing until it is started again.
              <AffectedBots bots={bots} />
            </>
          }
          confirmLabel={`Stop all ${total}`}
          confirmClass="bg-neg-muted text-neg-text border border-neg/40 hover:bg-neg/10"
          onConfirm={() => {
            stop.mutate()
            setConfirm(null)
          }}
          onCancel={() => setConfirm(null)}
          isPending={stop.isPending}
        />
      )}
      {confirm === 'restart' && (
        <ConfirmModal
          label={`Restart all ${total} bots?`}
          description={
            <>
              Each bot stops and comes back on the version it already has. An open position is
              restored from its own record.
              <AffectedBots bots={bots} />
            </>
          }
          confirmLabel={`Restart all ${total}`}
          confirmClass="bg-bg-surface text-text-primary border border-border-default hover:bg-bg-hover"
          onConfirm={() => {
            restart.mutate()
            setConfirm(null)
          }}
          onCancel={() => setConfirm(null)}
          isPending={restart.isPending}
        />
      )}
    </div>
  )
}
