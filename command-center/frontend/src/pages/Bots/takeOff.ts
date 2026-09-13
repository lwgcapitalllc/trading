import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useAssignBotAccount } from '@/hooks/useBots'

/** Stop the bot, wait until the box says it has, then run `then` — the page's stop-first flow bound
 *  to one bot. Resolves once it is over, whether or not `then` ran. */
export type StopFirst = (then: () => Promise<boolean>) => Promise<void> | void

/** Where one bot's take-off control is: at rest, armed by a first press, or at work. */
export type TakeOffState = 'idle' | 'armed' | 'removing'

/**
 * Taking a bot off its account — ONE flow for the bot panel and every row of the account panel.
 *
 * 🔴 Aaron, 2026-09-13: *"there should just be one button going from take off -> stop and take off
 * -> removing then modal close … keep it consistent whether I am on the account removing a bot or
 * I clicked on the bot."* Each panel had its own copy in its own words: a running bot's showed a
 * Stopping pill beside a greyed button, one fell back to its idle label mid-flow, neither closed.
 *
 * - The first press ARMS (disarming itself after 6s); the second takes it off, stopping a running
 *   bot first through the page's `stopThen` (`stopFirst`).
 * - From that second press until it is over the bot is `removing`. Written, a panel that passed
 *   `onClose` closes (the bot panel); one that stays open (the account panel, Aaron's call) lets go
 *   only once the account list has re-read and the bot has left its row — letting go at the write
 *   flashed Take off on a bot already off. Not written — refused, or it would not stop in time —
 *   its control comes back.
 * - ⚠ ONE at a time per panel (`busy`): the page holds a single stop-first wait.
 * - ⚠ The close is an EFFECT, never the flow's own callback: that closure holds the URL as it was at
 *   the press, so it would also close whatever the reader opened since. It runs with the panel's
 *   current `onClose`, only while the panel still shows `scope` (its bot, or its account), and never
 *   once the panel is gone.
 */
export function useTakeOff(scope: string, onClose?: () => void) {
  const assign = useAssignBotAccount()
  const qc = useQueryClient()

  const [armed, setArmed] = useState<string | null>(null)
  useEffect(() => {
    if (!armed) return
    const t = setTimeout(() => setArmed(null), 6_000)
    return () => clearTimeout(t)
  }, [armed])

  const [removal, setRemoval] = useState<{ scope: string; key: string; done: boolean } | null>(null)
  const here = removal?.scope === scope ? removal : null
  useEffect(() => {
    if (here?.done) onClose?.()
  }, [here, onClose])

  async function takeOff(key: string, display: string, stopFirst: StopFirst | null) {
    setRemoval({ scope, key, done: false })
    let written = false
    const write = async () => {
      // A refusal is `api.*`'s own toast; this only needs to know nothing was written.
      written = await assign.mutateAsync({ botKey: key, account: null, display }).then(
        () => true,
        () => false
      )
      // Staying open, wait for the account list's re-read — the write already asked for it, so
      // this joins that one — and the bot has left its row by the time the button lets go.
      if (written && !onClose)
        await qc.invalidateQueries(
          { queryKey: ['bots', 'accounts'], exact: true },
          { cancelRefetch: false }
        )
      return written
    }
    await (stopFirst ? stopFirst(write) : write())
    setRemoval((r) => (r?.key !== key ? r : written && onClose ? { ...r, done: true } : null))
  }

  return {
    /** What one bot's control shows. */
    stateOf: (key: string): TakeOffState =>
      here?.key === key ? 'removing' : armed === key ? 'armed' : 'idle',
    /** A take-off under way in this panel — every other one waits for it. */
    busy: here !== null,
    /** First press arms, the second takes it off. `stopFirst` is `null` for a bot not running. */
    press(key: string, display: string, stopFirst: StopFirst | null) {
      if (armed !== key) return setArmed(key)
      setArmed(null)
      void takeOff(key, display, stopFirst)
    },
  }
}
