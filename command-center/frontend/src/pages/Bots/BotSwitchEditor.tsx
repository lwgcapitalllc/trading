/**
 * A two-state setting on a running bot — today that is the stop protection, the switch that moves
 * a trade's stop up once it has gone far enough its way.
 *
 * 🔴 **THE MEASURED RESULT IS RENDERED BESIDE THE SWITCH, ALWAYS, AND THAT IS THE POINT OF THIS
 * FILE (2026-09-16).** Both switches this surface offers have been measured and both LOSE MONEY.
 * A protection switch offered bare reads as the prudent choice and gets turned on for that reason
 * — "protect the stop" is a sentence nobody argues with. So the number travels with the control:
 * the server sends it (`bot_params.RUNTIME_SWITCHES`) and this never renders a switch without it.
 * ⚠ The warning is the SERVER'S sentence. Do not write a second copy here — two copies of a
 * measurement drift, and the one on screen would be the one nobody re-measures.
 *
 * ⚠ **What OFF means is stated too.** Off is not "unset" — it is the shipped, measured-best state,
 * and a reader who cannot tell those apart will flip it to make the row look configured.
 * ⚠ **Turning it ON confirms; turning it OFF does not.** Off is the direction the measurement
 * points, and a confirmation on the safe direction trains a yes on the unsafe one.
 * ⚠ **Only the reader's EDIT is state**, bound to the value it was made against (`from`), so a
 * save landing — or anything else moving the value — drops the edit rather than saving over a
 * change nobody saw.
 */
import { useState } from 'react'
import { AlertTriangle, Loader2 } from 'lucide-react'
import { useSaveBotRuntime } from '@/hooks/useBots'
import type { BotParamRow } from '@/types'

export function BotSwitchEditor({
  botKey,
  botLabel,
  row,
  live,
}: {
  botKey: string
  /** Name plus LIVE or demo — this is where a live bot's exits are changed. */
  botLabel: string
  row: BotParamRow
  live: boolean
}) {
  const spec = row.switch
  const [confirming, setConfirming] = useState(false)
  const save = useSaveBotRuntime()
  // A switch with no measured sentence is not rendered at all — see the file header.
  if (!spec) return null

  const on = row.value === spec.on
  const name = row.label.replace(/^[\s↳]+/, '')

  const commit = (next: number | boolean) =>
    save.mutate(
      { botName: botKey, values: { [row.name]: next }, display: botLabel },
      { onSuccess: () => setConfirming(false) }
    )

  return (
    <div data-testid="bot-switch" data-name={row.name} data-on={on ? 'yes' : 'no'}>
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-[11px] text-text-tertiary">{name}</span>
        <button
          role="switch"
          aria-checked={on}
          aria-label={name}
          data-testid="switch-toggle"
          disabled={save.isPending}
          onClick={() => (on ? commit(spec.off) : setConfirming(true))}
          className={`relative w-[38px] h-[21px] rounded-full border transition-colors disabled:opacity-40 ${
            on ? 'bg-accent/30 border-accent/50' : 'bg-bg-sunken border-border-default'
          }`}
        >
          <span
            className={`absolute top-[2px] w-[15px] h-[15px] rounded-full transition-all ${
              on ? 'left-[20px] bg-accent-text' : 'left-[2px] bg-text-tertiary'
            }`}
          />
        </button>
        <span data-testid="switch-state" className="text-[11.5px] text-text-secondary">
          {on ? spec.on_label : 'Off — the stop stays where the trade started'}
        </span>
        {save.isPending && <Loader2 size={12} className="animate-spin text-text-tertiary" />}
      </div>

      {/* 🔴 The measurement, on screen, in both states. Hiding it while the switch is off would
       *  mean the reader meets the claim only after deciding to act on it. */}
      <p
        data-testid="switch-warn"
        className="flex gap-[6px] text-[11px] text-text-tertiary mt-[6px] leading-[1.5]"
      >
        <AlertTriangle size={11} className="shrink-0 mt-[2px] text-warn-text" />
        {spec.warn}
      </p>

      {confirming && (
        <div
          data-testid="switch-confirm"
          className={`mt-3 rounded-md border px-4 py-3 ${
            live ? 'border-warn/50 bg-warn-muted/40' : 'border-border-default bg-bg-sunken'
          }`}
        >
          <p className="text-[12.5px] font-semibold text-text-primary">
            Turn on {name.toLowerCase()} for {botLabel}
          </p>
          <p className="text-[11.5px] text-text-secondary mt-[6px] leading-[1.5]">
            {live
              ? 'This changes how every future trade ends — on real money — and the measurement above says it costs money.'
              : 'This changes how every future trade ends, and the measurement above says it costs money.'}
          </p>
          <p className="text-[11px] text-text-tertiary mt-[6px] leading-[1.5]">
            The bot is not restarted — it picks this up the next time it has no open trade.
          </p>
          <div className="flex items-center gap-2 mt-[10px]">
            <button
              data-testid="switch-confirm-go"
              disabled={save.isPending}
              onClick={() => commit(spec.on)}
              className={`inline-flex items-center gap-[6px] px-3 py-[6px] rounded-md text-[12px] font-semibold border transition-colors disabled:opacity-50 ${
                live
                  ? 'border-warn/70 bg-warn/15 text-warn-text hover:bg-warn/25'
                  : 'border-accent/50 bg-accent-muted text-accent-text hover:bg-accent/15'
              }`}
            >
              {save.isPending && <Loader2 size={12} className="animate-spin" />}
              {save.isPending ? 'Saving…' : live ? 'Turn it on — real money' : 'Turn it on'}
            </button>
            <button
              disabled={save.isPending}
              onClick={() => setConfirming(false)}
              className="px-3 py-[6px] rounded-md text-[12px] border border-border-default text-text-secondary hover:bg-bg-hover hover:text-text-primary transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
