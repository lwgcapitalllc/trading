/**
 * Setup — everything about a bot that you CHANGE, in one tab.
 *
 * 🔴 **This exists because the answer to *put this bot on that account and set how it trades* was
 * spread over three tabs.** Accounts assigned it, Configure set its risk and deployed it, Monitor
 * said whether it came up — and each of the three repeated the other two's version, account,
 * status and risk. Aaron, 2026-09-04: *"I have to go to one tab just to move bots to accounts,
 * another to configure single instances of a bot and another to have an overview. The UX is just
 * bad."*
 *
 * **Two panes, one tab, selected by `?bot=`:**
 *
 *   nothing selected -> the ACCOUNTS pane: which accounts exist, which bots are on each, the
 *                       account risk cap, add / move / remove.
 *   `?bot=<key>`     -> that bot's own pane: what is deployed, its risk per trade, its account
 *                       facts, its parameters.
 *
 * ⚠ **The two panes are the two halves of one job, not two features.** Assigning a bot is
 * immediately followed by setting how it trades — that is why the accounts pane's Configure
 * control now swaps this pane rather than navigating away, and why leaving the bot pane returns
 * you to the account you came from rather than to a list you have to search again.
 *
 * ⚠ **Selection lives in the URL, like every other tab state in this app.** A link to one bot's
 * setup is a real link, and a refresh does not silently move you to a different bot's Deploy
 * button. Keyed on `bot.key` and never the display name, for the reason `ConfigureTab` records:
 * a name is a label somebody eventually edits, and the thing a dead key falls back to is another
 * bot's controls with the URL still naming the one you wanted.
 *
 * ⚠ **`?tab=accounts` and `?tab=configure` still resolve here** — see `readTab` in `index.tsx`.
 * Both are in browser history and in links this app built for itself.
 */
import { useSearchParams } from 'react-router-dom'
import { ChevronLeft } from 'lucide-react'
import { useBotSnapshot, useBotVersions } from '@/hooks/useBots'
import { AccountsTab } from './AccountsTab'
import { BotPanel, FleetStrip, versionFlags } from './ConfigureTab'

export function SetupTab() {
  const { data: snapshot } = useBotSnapshot()
  const [params, setParams] = useSearchParams()

  const bots = snapshot?.bots ?? []
  const keys = bots.map((b) => b.key)

  // One fetch per bot, sharing every other reader's cache entries — see `useBotVersions`. Kept at
  // this level rather than inside the strip so the deploy state is read ONCE for the tab and the
  // two panes cannot disagree about what is deployed.
  const versionQueries = useBotVersions(keys)
  const flags = versionQueries.map((q) => versionFlags(q.data))
  const unreadable = versionQueries.filter((q) => !q.isPending && !q.data).length
  const loading = versionQueries.some((q) => q.isPending)
  const rechecking = versionQueries.some((q) => q.isFetching)

  // ⚠ An unknown key shows the ACCOUNTS pane rather than falling back to `bots[0]`. Falling back
  // is what `ConfigureTab` warns about: a stale link would open a different bot's Deploy button
  // while the URL still named the one you asked for.
  const requested = params.get('bot')
  const selected = requested ? (bots.find((b) => b.key === requested) ?? null) : null

  const select = (key: string | null) => {
    const next = new URLSearchParams(params)
    if (key === null) next.delete('bot')
    else next.set('bot', key)
    setParams(next, { replace: true })
  }

  if (!snapshot) return null
  if (bots.length === 0) {
    return <p className="text-[11px] text-text-tertiary">No bots registered.</p>
  }

  return (
    <div>
      {/* What needs deploying, across the whole fleet. It belongs to this tab rather than to
          Fleet: every count on it is answered by an action that lives here. Clicking one selects
          that bot, which is now a pane swap rather than a tab change. */}
      <FleetStrip
        bots={bots}
        flags={flags}
        unreadable={unreadable}
        loading={loading}
        rechecking={rechecking}
        onSelect={(key: string) => select(key)}
      />

      {selected ? (
        <div>
          {/* Back to the ACCOUNT, not to a list. The bot pane is entered from an account's row,
              so returning to a bare list would make the reader find their place again — and the
              account is where the next thing they do (move it, cap it, add another) lives. */}
          <button
            type="button"
            onClick={() => select(null)}
            className="inline-flex items-center gap-[4px] text-[11px] text-text-secondary
                       hover:text-text-primary cursor-pointer mb-[10px] transition-colors
                       duration-[100ms]"
          >
            <ChevronLeft size={12} />
            Accounts
          </button>

          <div className="pb-[10px] flex items-center gap-2 flex-wrap">
            <span className="text-[14px] font-semibold">{selected.name}</span>
            <span
              className={`inline-flex text-[10px] font-semibold px-2 py-[3px] rounded-pill uppercase tracking-[0.4px] ${
                selected.status === 'RUNNING'
                  ? 'bg-pos-muted text-pos-text'
                  : 'bg-neg-muted text-neg-text'
              }`}
            >
              {selected.status === 'RUNNING'
                ? 'Running'
                : selected.status === 'ERROR'
                  ? 'Error'
                  : 'Stopped'}
            </span>
            <span
              className={`inline-flex text-[10px] font-semibold px-2 py-[3px] rounded-pill uppercase tracking-[0.4px] ${
                selected.account_type === 'live'
                  ? 'bg-warn-muted text-warn-text'
                  : 'bg-bg-surface-2 text-text-secondary'
              }`}
            >
              {selected.account_type}
            </span>
            <span className="text-[11px] font-mono text-text-tertiary">{selected.account}</span>
          </div>

          {/* Keyed on the bot so switching bots REMOUNTS rather than re-rendering: the panel
              holds edit state (a typed risk %, an open confirm), and carrying that across a
              selection change would offer one bot's pending edit against another bot's controls. */}
          <BotPanel key={selected.key} bot={selected} />
        </div>
      ) : (
        <AccountsTab />
      )}
    </div>
  )
}
