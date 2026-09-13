import { Loader2, Unlink } from 'lucide-react'
import type { TakeOffState } from './takeOff'

/**
 * The take-off control — the bot panel's and each account-panel row's, the same words in the same
 * order (2026-09-13): Take off → Stop and take off (Confirm take off for a stopped bot) → Removing….
 * `useTakeOff` runs it; this only draws it, and says on the control itself why it cannot be
 * pressed.
 *
 * ⚠ Removing… keeps the confirm's colours at full strength. Faded like a disabled control, it read
 *   as one that had died rather than one at work.
 * ⚠ `compact` is the account panel's row: no icon beside the words, so the longest fits its 136px
 *   column — which the row gives it whole while it is armed or at work.
 */
export function TakeOffButton({
  testId,
  state,
  display,
  account,
  running,
  holding = false,
  unknown = false,
  blocked = false,
  compact = false,
  onPress,
}: {
  testId: string
  state: TakeOffState
  /** What the bot is called on screen. */
  display: string
  /** The account it would come off. */
  account: number | null
  running: boolean
  /** It holds a trade — taken off now, nothing would manage it. */
  holding?: boolean
  /** The trading box has not answered for it, so whether it runs is not known. */
  unknown?: boolean
  /** Something else is under way — another take-off, a start or a stop. */
  blocked?: boolean
  compact?: boolean
  onPress: () => void
}) {
  const removing = state === 'removing'
  const title = removing
    ? `Taking ${display} off account ${account}.`
    : unknown
      ? `The trading box has not answered for ${display} — wait for its state before taking it off.`
      : holding
        ? `${display} holds a trade, so it stays on this account until the trade closes — taken off now, nothing would manage that trade.`
        : state === 'armed'
          ? running
            ? 'Click again: it is stopped first, then taken off the account.'
            : 'Click again to take it off the account.'
          : `Take ${display} off account ${account}. ${running ? 'It is running, so it is stopped first. ' : ''}It stays registered and stopped until you add it to an account again.`
  return (
    <button
      data-testid={testId}
      disabled={removing || unknown || holding || blocked}
      aria-busy={removing || undefined}
      title={title}
      onClick={onPress}
      className={`flex items-center gap-[6px] rounded-md border whitespace-nowrap transition-colors disabled:cursor-not-allowed ${
        compact ? 'px-[9px] h-[26px] text-[11.5px]' : 'px-3 py-[6px] text-small'
      } ${
        removing
          ? 'border-warn/40 bg-warn-muted text-warn-text'
          : state === 'armed'
            ? 'border-warn/40 bg-warn-muted text-warn-text hover:bg-warn/10 disabled:opacity-40'
            : 'border-border-default text-text-secondary hover:bg-bg-hover hover:text-text-primary disabled:opacity-40'
      }`}
    >
      {removing ? (
        <Loader2 size={12} className="animate-spin" />
      ) : compact ? null : (
        <Unlink size={12} />
      )}
      {removing
        ? 'Removing…'
        : state === 'armed'
          ? running
            ? 'Stop and take off'
            : 'Confirm take off'
          : 'Take off'}
    </button>
  )
}
