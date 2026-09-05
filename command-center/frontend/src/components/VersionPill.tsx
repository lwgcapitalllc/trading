import { AlertTriangle, CheckCircle2, HelpCircle } from 'lucide-react'
import type { BotDeployedVersion } from '@/types'

/**
 * ONE pill for "what version of this bot is deployed", used everywhere a bot is listed.
 *
 * Aaron, 2026-08-09: *"there should be a column even on the monitor page showing the bot version
 * that's running… Same thing on the accounts page. Everything should be aligned. All the versions.
 * Create a pill that looks clean across all."* So this is a component rather than a snippet copied
 * into two tables — the Configure tab already renders the same numbers as a full banner, and three
 * hand-written readings of one deployment claim is three answers that can disagree.
 *
 * ⚠ **It reports the DEPLOYED version, never the local one.** `v121` in the backtester is not
 * running anywhere; the number a row on a fleet page has to answer for is what is on the box. The
 * repo's number appears only inside the "behind" state, where it is the thing being subtracted.
 *
 * ⚠ **Three states, and the third may never be rendered as a number.** Up to date, behind by N, or
 * UNKNOWN — never promoted, the deployed commit not fetched on this machine, no git. `v0` would be
 * the reassuring answer to a question nobody could answer, which is the same rule `mt5_link` and
 * `grid_sensitivity_score` follow. A version display that can be quietly wrong is worse than none,
 * because it is what you check before deciding anything.
 *
 * 🔴 **All three states carry a BORDER, and the up-to-date one is green (2026-09-05).** It was
 * `bg-bg-surface-2 text-text-secondary` — the same grey as the surface behind it — so on a page
 * where every other column is also grey the version stopped registering as a claim at all. Aaron:
 * *"the version of the bot, outline that with some kind of colour or something, so it stands out
 * to me."*
 *
 * ⚠ **Green means UP TO DATE, never "good bot".** It is answering one question — is the box
 * running the code you tested — and that is the only thing it may ever be read as. ⚠ **The unknown
 * state stays NEUTRAL and gets a border too**: it must not borrow either verdict's colour, and
 * without a border it is the one state that looks like a rendering failure rather than a finding.
 */
export function VersionPill({
  version,
  loading,
}: {
  version: BotDeployedVersion | null | undefined
  /** The query has not answered yet. Distinct from "answered, cannot say" — one is a wait and
   *  the other is a finding, and an em-dash for both makes a slow fetch look like a fault. */
  loading?: boolean
}) {
  if (loading) {
    return <span className="text-micro text-text-tertiary">checking…</span>
  }

  const c = version?.compare ?? null
  if (!c || !c.comparable || c.deployed_version === null) {
    return (
      <span
        data-testid="version-pill"
        data-state="unknown"
        title={c?.reason || 'Could not work out which version this bot is running.'}
        className="inline-flex items-center gap-[3px] text-[10px] font-semibold px-2 py-[3px]
                   rounded-pill uppercase tracking-[0.4px] bg-bg-surface-2 text-text-tertiary
                   border border-border-strong cursor-default"
      >
        <HelpCircle size={9} /> No version
      </span>
    )
  }

  const behind = c.versions_behind ?? 0
  const label = `v${c.deployed_version}`

  return (
    <span
      data-testid="version-pill"
      data-state={behind > 0 ? 'behind' : 'current'}
      title={
        behind > 0
          ? `Deployed v${c.deployed_version}, backtester on v${c.local_version} — ` +
            `${behind} change${behind === 1 ? '' : 's'} to this bot's code waiting to go out. ` +
            `Deploy it from Configure.`
          : `Deployed v${c.deployed_version} — the same code the backtester runs.`
      }
      className={`inline-flex items-center gap-[3px] text-[10px] font-semibold px-2 py-[3px]
                  rounded-pill uppercase tracking-[0.4px] border cursor-default ${
                    behind > 0
                      ? 'bg-warn-muted text-warn-text border-warn/50'
                      : 'bg-pos-muted text-pos-text border-pos/40'
                  }`}
    >
      {behind > 0 ? <AlertTriangle size={9} /> : <CheckCircle2 size={9} />}
      {label}
      {behind > 0 ? ` · ${behind} behind` : ''}
    </span>
  )
}
