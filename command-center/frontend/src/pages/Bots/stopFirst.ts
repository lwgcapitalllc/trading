import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useBotStartOne, useBotStopOne } from '@/hooks/useBots'
import type { BotSnapshot } from '@/types'
import type { BotAction } from './BotStatusPill'

/** How long a stop may take before the follow-up is abandoned, and how often the box is re-read.
 *  The runner checks its stop file every 10s and is usually gone inside 30s. */
export const STOP_WAIT_MS = 90_000
export const STOP_POLL_MS = 5_000

/**
 * Stop a bot, WAIT until the trading box says it is no longer running, then do the thing that
 * needed it stopped — take it off its account, or move it (2026-09-13) — and, for a move onto a
 * demo account, START it again once the move has gone through.
 *
 * 🔴 Aaron: *"it is not intuitive that you have to stop a bot to remove from account … maybe the
 * remove button should always be there and when we click then it says are you sure bot will be
 * stopped first?"* The rule under it stands — a bot reads its account when it starts, so the
 * server refuses the write while it runs (409) — but the reader no longer carries it out by hand.
 *
 * 🔴 **A moved bot is started again** (Aaron, the same day: *"let them automatically start"*). A
 * move changes WHERE a bot trades, not WHETHER: `restart` starts it once `then` reports the write
 * went through. ⚠ **Only on `true`** — a write that failed leaves it stopped and says so, because
 * the page stopped it only to make that write. ⚠ **The caller decides**: a live destination does
 * not pass `restart`, so the first real-money start stays a click.
 *
 * ⚠ **The stop only ASKS.** `POST /bots/{key}/stop` writes the bot's stop file and returns; the bot
 * finishes what it is doing and exits on its next check. So the follow-up waits for the SNAPSHOT to
 * say so, re-reading it every `STOP_POLL_MS`.
 * ⚠ **Never on a guess.** A bot the box has not answered for, or one still running at
 * `STOP_WAIT_MS`, gets no follow-up: it was asked to stop, and the message says nothing moved.
 * ⚠ **It lives on the PAGE, never in a panel**, so closing the panel mid-wait cannot leave a bot
 * stopped and still on its account.
 */
export function useStopFirst() {
  const qc = useQueryClient()
  const stop = useBotStopOne()
  const start = useBotStartOne()
  // Which bot, and what its row says it is doing: 'stop' while the box catches up, `null` while the
  // write runs (its own control says so), 'start' while it is started again.
  const [waiting, setWaiting] = useState<{ key: string; action: BotAction | null } | null>(null)

  /** `what` finishes "…so it was not ___" when the bot will not stop in time. `then` makes the write
   *  and, when `restart` is asked for, returns whether it went through. */
  async function stopThen(
    key: string,
    label: string,
    what: string,
    then: () => Promise<boolean> | boolean | void,
    opts: { restart?: boolean } = {}
  ) {
    setWaiting({ key, action: 'stop' })
    try {
      await stop.mutateAsync(key)
      const deadline = Date.now() + STOP_WAIT_MS
      for (;;) {
        const status = qc
          .getQueryData<BotSnapshot>(['bots', 'snapshot'])
          ?.bots.find((b) => b.key === key)?.status
        if (status !== undefined && status !== 'RUNNING') break
        if (Date.now() >= deadline) {
          toast.error(
            `${label} has not stopped yet, so it was not ${what}. It was asked to stop — try again once it has.`
          )
          return
        }
        await new Promise((r) => setTimeout(r, STOP_POLL_MS))
        await qc.refetchQueries({ queryKey: ['bots', 'snapshot'] })
      }
      setWaiting({ key, action: null })
      const done = await then()
      if (!opts.restart) return
      if (done !== true) {
        toast.error(
          `${label} was stopped to be ${what}, and that did not go through, so it is left stopped. Start it again from its panel.`
        )
        return
      }
      setWaiting({ key, action: 'start' })
      await start.mutateAsync(key)
    } catch {
      // The stop or the start failed, and its own toast says why. Nothing further is done.
    } finally {
      setWaiting(null)
    }
  }

  return {
    stopThen,
    waitingFor: waiting?.key ?? null,
    waitingAction: waiting?.action ?? null,
  }
}
