import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useBotStopOne } from '@/hooks/useBots'
import type { BotSnapshot } from '@/types'

/** How long a stop may take before the follow-up is abandoned, and how often the box is re-read.
 *  The runner checks its stop file every 10s and is usually gone inside 30s. */
export const STOP_WAIT_MS = 90_000
export const STOP_POLL_MS = 5_000

/**
 * Stop a bot, WAIT until the trading box says it is no longer running, then do the thing that
 * needed it stopped — take it off its account, or move it (2026-09-13).
 *
 * 🔴 Aaron: *"it is not intuitive that you have to stop a bot to remove from account … maybe the
 * remove button should always be there and when we click then it says are you sure bot will be
 * stopped first?"* The rule under it stands — a bot reads its account when it starts, so the
 * server refuses the write while it runs (409) — but the reader no longer carries it out by hand.
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
  const [waitingFor, setWaitingFor] = useState<string | null>(null)

  /** `what` finishes the sentence "…so it was not ___" when the bot will not stop in time. */
  async function stopThen(key: string, label: string, what: string, then: () => void) {
    setWaitingFor(key)
    try {
      await stop.mutateAsync(key)
      const deadline = Date.now() + STOP_WAIT_MS
      for (;;) {
        const status = qc
          .getQueryData<BotSnapshot>(['bots', 'snapshot'])
          ?.bots.find((b) => b.key === key)?.status
        if (status !== undefined && status !== 'RUNNING') {
          then()
          return
        }
        if (Date.now() >= deadline) {
          toast.error(
            `${label} has not stopped yet, so it was not ${what}. It was asked to stop — try again once it has.`
          )
          return
        }
        await new Promise((r) => setTimeout(r, STOP_POLL_MS))
        await qc.refetchQueries({ queryKey: ['bots', 'snapshot'] })
      }
    } catch {
      // The stop itself failed, and its own toast says why. Nothing further is done.
    } finally {
      setWaitingFor(null)
    }
  }

  return { stopThen, waitingFor }
}
