/**
 * A bot's risk per trade — the one setting a running bot takes without a restart — edited where it
 * belongs.
 *
 * 🔴 **On an account, a bot's risk is a SHARE of the account's budget, so it is checked and saved
 * WITH that budget (2026-09-11).** It saved through the bot's own runtime endpoint, which could
 * refuse a raise on a full account and offered no way out — the reader had to find the account
 * panel, raise the cap there, come back and try again. The plan under the box now says whether the
 * new share fits, and a refused raise offers "also raise the account cap" in the SAME save
 * (`PATCH /bots/accounts/{a}/risk`). A bot on NO account keeps the runtime endpoint — it has no
 * budget to share.
 *
 * ⚠ **Whether it fits is the server's answer** (`useAccountRiskPlan`), and so is the cap it would
 * take (`fit_cap`). The page never adds shares up.
 * ⚠ **The confirmation is a STEP in the panel, never a modal** (Aaron, 2026-09-10: *"I'd rather not
 * go from a side drawer to a modal"*). It carries the numbers — `5% → 4%`, the dollars per trade —
 * because "are you sure?" trains a yes and a number is read. On a live account its button says real
 * money.
 * ⚠ **Only the reader's EDIT is state**, bound to the value it was made against (`from`), so a
 * save landing — or anything else moving the value — drops the edit rather than saving over a
 * change nobody saw.
 */
import { useState } from 'react'
import { AlertTriangle, ArrowUp, Loader2 } from 'lucide-react'
import { useAccountRiskPlan, useSaveAccountRisk, useSaveBotRuntime } from '@/hooks/useBots'
import type { BotAccountGroup, BotParamRow } from '@/types'
import { DecimalInput } from '@/components/DecimalInput'
import { useDebounced } from '@/lib/useDebounced'
import { pct } from './joinAccount'

const usd = (n: number) => '$' + n.toLocaleString('en-US', { maximumFractionDigits: 0 })

export function BotRiskEditor({
  botKey,
  botLabel,
  row,
  balance,
  account,
  group,
  live,
  onOpenAccount,
}: {
  botKey: string
  /** Name plus LIVE or demo — this is where a live bot's risk is changed. */
  botLabel: string
  row: BotParamRow
  balance: number | null
  /** The account the bot's CONFIG names: `null` on none, `undefined` while the configs load. */
  account: number | null | undefined
  /** That account's group — its budget. Absent for a setting that is not the risk share. */
  group: BotAccountGroup | undefined
  live: boolean
  onOpenAccount?: (account: number) => void
}) {
  const current = Number(row.value)
  const unit = row.unit ?? '%'
  const fmt = (v: number | null) => (v == null ? '—' : `${+v.toFixed(2)}${unit}`)

  const [edit, setEdit] = useState<{ value: number | null; from: number } | null>(null)
  const draft = edit && edit.from === current ? edit.value : current
  // "Also raise the cap" — bound to the share it was offered for, so editing the share again
  // drops it rather than carrying a cap the new share may not need.
  const [raise, setRaise] = useState<{ cap: number; forDraft: number | null } | null>(null)
  const [confirming, setConfirming] = useState(false)
  const saveRisk = useSaveAccountRisk()
  const saveRuntime = useSaveBotRuntime()
  const pending = saveRisk.isPending || saveRuntime.isPending

  const inRange =
    draft != null &&
    Number.isFinite(draft) &&
    (row.min == null || draft >= row.min) &&
    (row.max == null || draft <= row.max)
  const dirty = inRange && draft !== current
  const budgeted = typeof account === 'number' && group?.kind === 'account'
  const raiseCap = raise && raise.forDraft === draft ? raise.cap : null
  const statedCap = group?.cap_agrees ? group.risk_cap_pct : null

  const body =
    budgeted && dirty
      ? {
          shares: { [botKey]: draft as number },
          ...(raiseCap != null ? { risk_cap_pct: raiseCap } : {}),
        }
      : null
  const asked = useDebounced(body, 250)
  const plan = useAccountRiskPlan(budgeted ? (account as number) : null, asked)
  const sameBody = JSON.stringify(asked) === JSON.stringify(body)
  const p = plan.data && !plan.isPlaceholderData && sameBody && body ? plan.data : undefined
  // A plan that could not be asked does not block the save — the server checks it again.
  const planFailed = plan.isError && sameBody && body !== null
  const checking = budgeted && dirty && !p && !planFailed

  const canSave =
    dirty && account !== undefined && !pending && (!budgeted || (p ? !p.refused : planFailed))
  const bigger = draft != null && draft > current

  const commit = () => {
    if (draft == null) return
    const done = {
      onSuccess: () => {
        setConfirming(false)
        setEdit(null)
        setRaise(null)
      },
    }
    if (budgeted)
      saveRisk.mutate(
        {
          account: account as number,
          shares: { [botKey]: draft },
          ...(raiseCap != null ? { riskCapPct: raiseCap } : {}),
        },
        done
      )
    else
      saveRuntime.mutate(
        { botName: botKey, values: { [row.name]: draft }, display: botLabel },
        done
      )
  }

  return (
    <div data-testid="bot-risk">
      <div className="flex items-end gap-4 flex-wrap">
        <div>
          <p className="text-[11px] text-text-tertiary mb-[4px]">{row.label}</p>
          <div className="flex items-baseline gap-[3px]">
            <span
              data-testid="risk-current"
              className="text-[26px] leading-none font-mono tabular-nums text-text-primary"
            >
              {+current.toFixed(2)}
            </span>
            <span className="text-[13px] text-text-tertiary">{unit}</span>
          </div>
          {balance != null && balance > 0 && unit === '%' && (
            <p className="text-[11px] text-text-tertiary mt-[5px]">
              ≈ {usd((balance * current) / 100)} a trade at {usd(balance)}
            </p>
          )}
        </div>

        <div className="ml-auto flex items-end gap-2">
          <label className="flex flex-col gap-[4px]">
            <span className="text-[11px] text-text-tertiary">Change to</span>
            <DecimalInput
              value={draft}
              onChange={(v) => {
                setEdit({ value: v, from: current })
                setConfirming(false)
              }}
              suffix={unit}
              invalid={draft != null && !inRange}
              aria-label={`New ${row.label.toLowerCase()}`}
              data-testid="risk-input"
              className="w-[100px]"
            />
          </label>
          <button
            data-testid="risk-save"
            disabled={!canSave || confirming}
            onClick={() => setConfirming(true)}
            className="px-4 h-[32px] rounded-md text-[12.5px] font-medium bg-accent-muted text-accent-text border border-accent/40 hover:bg-accent/15 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Save
          </button>
        </div>
      </div>

      {draft != null && !inRange && (
        <p className="text-[11px] text-neg-text mt-[6px]">
          Between {row.min} and {row.max}
          {unit}.
        </p>
      )}

      {/* ── what the account's budget says about it ─────────────────────────── */}
      {budgeted && dirty && (
        <div data-testid="risk-plan" className="mt-[10px] text-[11.5px] leading-[1.5]">
          {checking ? (
            <span className="inline-flex items-center gap-[6px] text-text-tertiary">
              <Loader2 size={11} className="animate-spin" />
              Checking account {account}&rsquo;s cap…
            </span>
          ) : planFailed ? (
            <span className="text-text-tertiary">
              Could not check account {account}&rsquo;s cap — the save is checked again when you
              confirm.
            </span>
          ) : p?.refused ? (
            <div className="rounded-md border border-warn/40 bg-warn-muted/50 px-3 py-[8px]">
              <p className="flex gap-[6px] text-warn-text">
                <AlertTriangle size={12} className="shrink-0 mt-[2px]" />
                {p.refused}
              </p>
              <div className="flex flex-wrap items-center gap-2 mt-[8px]">
                {p.fit_cap != null && (
                  <button
                    data-testid="risk-raise-cap"
                    onClick={() => setRaise({ cap: p.fit_cap as number, forDraft: draft })}
                    className="inline-flex items-center gap-[5px] px-[10px] py-[5px] rounded-md text-[11.5px] font-medium border border-accent/40 text-accent-text hover:bg-accent/15 transition-colors"
                  >
                    <ArrowUp size={11} /> Also raise the account cap to {pct(p.fit_cap)}
                  </button>
                )}
                {onOpenAccount && typeof account === 'number' && (
                  <button
                    onClick={() => onOpenAccount(account)}
                    className="px-[10px] py-[5px] rounded-md text-[11.5px] border border-border-default text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors"
                  >
                    Or lower another bot on account {account}
                  </button>
                )}
              </div>
            </div>
          ) : p ? (
            p.fits ? (
              <span className="text-text-secondary">
                {p.risk_cap_pct == null ? (
                  <>No cap on account {account} — nothing to fit under.</>
                ) : (
                  <>
                    Fits — the bots on account {account} would risk{' '}
                    <b className="text-text-primary">{pct(p.share_total_pct)}</b> of its{' '}
                    {pct(p.risk_cap_pct)} cap.
                  </>
                )}
              </span>
            ) : (
              <span className="text-text-secondary">
                Account {account} is still over its cap, but this lowers the risk, so it can be
                saved.
              </span>
            )
          ) : null}
          {raiseCap != null && (
            <p
              data-testid="risk-raise-on"
              className="mt-[6px] flex items-center gap-2 text-text-secondary"
            >
              <ArrowUp size={11} className="text-accent-text" />
              The account&rsquo;s cap goes {pct(statedCap)} → {pct(raiseCap)} in the same save.
              <button
                onClick={() => setRaise(null)}
                className="text-text-tertiary underline underline-offset-2 hover:text-text-primary"
              >
                Undo
              </button>
            </p>
          )}
        </div>
      )}

      {/* ── the confirmation, with the numbers ───────────────────────────────── */}
      {confirming && draft != null && (
        <div
          data-testid="risk-confirm"
          className={`mt-3 rounded-md border px-4 py-3 ${
            live ? 'border-warn/50 bg-warn-muted/40' : 'border-border-default bg-bg-sunken'
          }`}
        >
          <p className="text-[12.5px] font-semibold text-text-primary">
            Change {row.label.toLowerCase()} on {botLabel}
          </p>
          <div className="flex items-baseline gap-3 mt-[8px] font-mono tabular-nums">
            <span className="text-[19px] text-text-tertiary">{fmt(current)}</span>
            <span className="text-text-tertiary">→</span>
            <span className={`text-[19px] ${bigger ? 'text-warn-text' : 'text-text-primary'}`}>
              {fmt(draft)}
            </span>
            {balance != null && balance > 0 && unit === '%' && (
              <span className="text-[11.5px] text-text-tertiary ml-1">
                {usd((balance * current) / 100)} → {usd((balance * draft) / 100)} a trade
              </span>
            )}
          </div>
          {raiseCap != null && (
            <p className="text-[11.5px] text-text-secondary mt-[6px]">
              Account {account}&rsquo;s cap {pct(statedCap)} → {pct(raiseCap)}, for every bot on it.
            </p>
          )}
          {bigger && (
            <p className="flex gap-[6px] text-[11.5px] text-warn-text mt-[6px]">
              <AlertTriangle size={12} className="shrink-0 mt-[2px]" />
              {live
                ? 'This raises the risk on every future trade — on real money.'
                : 'This raises the risk on every future trade.'}
            </p>
          )}
          <p className="text-[11px] text-text-tertiary mt-[6px] leading-[1.5]">
            {p?.applies ||
              'The bot is not restarted — it picks this up the next time it has no open trade.'}
          </p>
          <div className="flex items-center gap-2 mt-[10px]">
            <button
              data-testid="risk-confirm-go"
              disabled={pending}
              onClick={commit}
              className={`inline-flex items-center gap-[6px] px-3 py-[6px] rounded-md text-[12px] font-semibold border transition-colors disabled:opacity-50 ${
                live
                  ? 'border-warn/70 bg-warn/15 text-warn-text hover:bg-warn/25'
                  : 'border-accent/50 bg-accent-muted text-accent-text hover:bg-accent/15'
              }`}
            >
              {pending && <Loader2 size={12} className="animate-spin" />}
              {pending ? 'Saving…' : live ? 'Confirm — real money' : 'Confirm change'}
            </button>
            <button
              disabled={pending}
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
