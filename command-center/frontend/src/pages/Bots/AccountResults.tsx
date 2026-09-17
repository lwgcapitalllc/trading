/**
 * One broker account's REAL results — `/bots/accounts/:account`, opened from the account panel.
 *
 * Everything here comes off MT5's own deal history (`GET /bots/accounts/{n}/history`), not off any
 * bot's claim about itself: the balance over time with deposits and withdrawals marked, the growth
 * with those taken out, every trade on the price chart, and the backtest page's own analysis
 * panels read over the account's trades.
 *
 * 🔴 **Where the record came from is always on screen.** The box's own files and the git backup
 * render identically otherwise, and a backup an hour old must never pass for live.
 * ⚠ **The panels read the trades with deposits and withdrawals removed**, re-based on the money put
 * in. A withdrawal is not a drawdown, and a deposit is not a win.
 * ⚠ **Nothing recorded is its own state** — never a chart of zero.
 */
import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, RefreshCw } from 'lucide-react'
import {
  useAccountCandles,
  useAccountHistory,
  useRefreshAccountHistory,
  useBotSnapshot,
  useRegisteredAccounts,
} from '@/hooks/useBots'
import {
  DailyPnlChart,
  DirectionBreakdown,
  DrawdownChart,
  EquityCurveChart,
  PerformancePanel,
  SeriesToggle,
} from '@/components/runAnalysis/panels'
import { PriceChartView } from '@/components/runAnalysis/PriceChartView'
import { RDistribution } from '@/components/runAnalysis/RDistribution'
import { runFromBook, tradingEquity } from '@/components/runAnalysis/bookRun'
import { XModeToggle } from '@/components/XModeToggle'
import { getXMode, setXModePref, type XMode } from '@/lib/chartAxis'
import { C } from '@/themes/chart'
import type { AccountHistory } from '@/types'
import { accountName } from './AccountForm'
import { KindBadge } from './kind'
import { Shimmer } from '@/components/Shimmer'

// The second line is a SERIES, not an action — the stack page's leg palette, not the accent.
const TWR_COLOR = C.series[3]

const cardCls = 'rounded-lg border border-border-subtle bg-bg-surface p-4'
const headCls = 'text-[11px] font-semibold text-text-secondary uppercase tracking-[0.7px] mb-2'

function money(n: number | null | undefined, signed = false): string {
  if (n == null) return '—'
  const s = Math.abs(n).toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  const sign = n < 0 ? '−' : signed && n > 0 ? '+' : ''
  return `${sign}$${s}`
}

function when(ms: number | null | undefined): string {
  if (ms == null) return '—'
  return new Date(ms).toLocaleString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function ago(ms: number | null | undefined, now: number): string {
  if (ms == null) return ''
  const min = Math.round((now - ms) / 60_000)
  if (min < 1) return 'just now'
  if (min < 90) return `${min} min ago`
  const h = Math.round(min / 60)
  if (h < 48) return `${h} h ago`
  return `${Math.round(h / 24)} days ago`
}

/** Where the record came from, and how new its newest deal is. Always drawn. */
function SourceStrip({ h }: { h: AccountHistory }) {
  const live = h.source === 'box'
  // Grey when it is the box (the normal state), amber when it is the backup (needs a look).
  const cls = live
    ? 'border-border-subtle bg-bg-surface text-text-secondary'
    : 'border-warn/40 bg-warn-muted text-warn-text'
  return (
    <div
      data-testid="history-source"
      data-source={h.source ?? 'none'}
      className={`rounded-md border px-3 py-2 text-[12px] ${cls}`}
    >
      <span className="font-semibold">
        {live
          ? 'Read from the trading box'
          : h.source === 'archive'
            ? 'Read from the git backup'
            : 'No record found'}
      </span>
      {h.newest_deal_ms != null && (
        <span>
          {' '}
          · newest deal {when(h.newest_deal_ms)} ({ago(h.newest_deal_ms, h.read_at_ms)})
        </span>
      )}
      <span> · read {when(h.read_at_ms)}</span>
      {h.source_note && <div className="mt-1">{h.source_note}</div>}
    </div>
  )
}

function Stat({
  label,
  value,
  tip,
  cls,
}: {
  label: string
  value: string
  tip?: string
  cls?: string
}) {
  return (
    <div className="min-w-[130px]" title={tip}>
      <div className="text-[10px] uppercase tracking-[0.6px] text-text-tertiary">{label}</div>
      <div
        className={`text-[18px] font-semibold font-mono tabular-nums ${cls ?? 'text-text-primary'}`}
      >
        {value}
      </div>
    </div>
  )
}

export function AccountResults() {
  const params = useParams()
  const navigate = useNavigate()
  const account = params.account && /^\d+$/.test(params.account) ? Number(params.account) : null
  const { data: h, isLoading, isError, error } = useAccountHistory(account)
  const refresh = useRefreshAccountHistory(account)
  const { data: registry } = useRegisteredAccounts()
  const reg = registry?.find((r) => r.account === account)
  // MT5's live balance, off the Bots page's own snapshot — which shows a bot's balance only when it
  // was read on the account that bot is on. Three answers: matches, does not, or cannot say (null).
  const { data: snap, isLoading: snapLoading } = useBotSnapshot()
  const brokerBalance =
    snap?.bots.find((b) => Number(b.account) === account && b.balance != null)?.balance ?? null
  const brokerMatches =
    brokerBalance == null || h?.balance == null ? null : Math.abs(brokerBalance - h.balance) <= 0.01
  const symbol = h?.chart?.instrument || null
  const requestCandles = useAccountCandles(account, symbol)

  const [xMode, setXMode] = useState<XMode>(() => getXMode())
  const [histOn, setHistOn] = useState(false)
  const [fullscreen, setFullscreen] = useState(false)

  const points = useMemo(() => h?.equity ?? [], [h])
  const base = h?.capital_in ?? 0
  // The panels grade the STRATEGY: a trade the record marks as not its own (a duplicate-order
  // incident, a hand mark) stays on the balance curve and the chart, and out of every figure here.
  const scored = useMemo(() => points.filter((p) => !p.excluded), [points])
  const book = useMemo(() => tradingEquity(scored, base), [scored, base])
  const { run, fallback } = useMemo(() => runFromBook(scored), [scored])
  const markers = useMemo(() => {
    if (!h) return []
    // One marker per DAY: moves on one day sit on one x and their labels printed over each other.
    const byDay = new Map<string, { date: string; time_ms: number; net: number; n: number }>()
    for (const f of h.flows) {
      const day = f.date.slice(0, 10)
      const g = byDay.get(day) ?? { date: f.date, time_ms: f.time_ms, net: 0, n: 0 }
      g.net += f.amount
      g.n += 1
      g.time_ms = Math.max(g.time_ms, f.time_ms)
      byDay.set(day, g)
    }
    return [...byDay.values()].map((g) => {
      const next = points.find((p) => (p.exit_ms ?? 0) >= g.time_ms)
      const verb = g.n > 1 ? `Net ${g.net >= 0 ? '+' : '-'}` : g.net >= 0 ? 'In ' : 'Out '
      return {
        date: g.date,
        tradeIndex: next?.index ?? (points.length ? points[points.length - 1].index : 1),
        label: `${verb}${money(Math.abs(g.net))}${g.n > 1 ? ` (${g.n} moves)` : ''}`,
        // Grey: money moved is neither a result nor something to click.
        color: C.axisTick,
      }
    })
  }, [h, points])

  const title = accountName(reg) ?? (account !== null ? `Account ${account}` : 'Account')

  return (
    <div className="space-y-4" data-testid="account-results">
      <div className="flex items-center gap-3 flex-wrap">
        <button
          onClick={() => navigate('/bots')}
          className="flex items-center gap-1 text-[13px] text-text-secondary hover:text-text-primary"
        >
          <ArrowLeft size={14} /> Bots
        </button>
        <h1 className="text-[18px] font-semibold text-text-primary">{title}</h1>
        {account !== null && <span className="text-[12px] text-text-tertiary">#{account}</span>}
        <KindBadge kind={reg?.kind} />
        <div className="flex-1" />
        <button
          data-testid="history-refresh"
          disabled={refresh.isPending || account === null}
          onClick={() => refresh.mutate()}
          title="Read the box again now, skipping the one-minute cache"
          className="flex items-center gap-1 rounded-md border border-border-default px-2 py-1 text-[12px] text-text-secondary hover:bg-bg-hover disabled:opacity-50"
        >
          <RefreshCw size={12} className={refresh.isPending ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      {account === null && <div className={cardCls}>That is not an account number.</div>}
      {isLoading && (
        <div data-testid="history-loading" className="space-y-4">
          <Shimmer className="h-[38px] w-full" />
          <Shimmer className="h-[74px] w-full" />
          <Shimmer className="h-[340px] w-full" />
        </div>
      )}
      {isError && (
        <div className={`${cardCls} text-neg-text`}>
          Could not read this account's history: {(error as Error)?.message ?? 'unknown error'}
        </div>
      )}

      {h && <SourceStrip h={h} />}

      {h?.status === 'no_history' && (
        <div data-testid="history-empty" className={`${cardCls} text-[13px] text-text-secondary`}>
          {h.reason}
        </div>
      )}

      {h?.status === 'ok' && (
        <>
          <div className={`${cardCls} flex flex-wrap gap-6`}>
            <Stat
              label="Balance"
              value={money(h.balance)}
              tip="What the deals add up to, credit left out."
            />
            <Stat
              label="Money in"
              value={money(h.capital_in)}
              tip="Every deposit less every withdrawal."
            />
            <Stat
              label="Trading P&L"
              value={money(h.trading_pnl, true)}
              cls={(h.trading_pnl ?? 0) >= 0 ? 'text-pos-text' : 'text-neg-text'}
              tip="What the closed trades made, costs included. Deposits and withdrawals are not in it."
            />
            <Stat
              label="Growth excl. deposits"
              value={
                h.twr_pct != null ? `${h.twr_pct >= 0 ? '+' : ''}${h.twr_pct.toFixed(2)}%` : '—'
              }
              tip={
                h.twr_reason ??
                'Time-weighted: the return between one deposit or withdrawal and the next, chained — so when money arrived does not move it.'
              }
            />
            <Stat label="Closed trades" value={String(points.length)} />
            <Stat
              label="Manual trades"
              value={String(h.manual_trades ?? 0)}
              tip="Positions no bot recorded opening. They have no recorded stop, so no R."
            />
          </div>

          {(h.reconciled === false ||
            (h.excluded_trades ?? 0) > 0 ||
            brokerMatches === false ||
            (brokerMatches == null && !snapLoading) ||
            (h.open_positions ?? 0) > 0 ||
            (h.adjustments_total ?? 0) !== 0 ||
            (h.unmatched_plans ?? 0) > 0 ||
            h.bars_note) && (
            <div className="rounded-md border border-warn/40 bg-warn-muted px-3 py-2 text-[12px] text-warn-text space-y-1">
              {h.reconciled === false && (
                <div>
                  The deals do not add up to their own balance — a figure on this page is wrong.
                </div>
              )}
              {(h.excluded_trades ?? 0) > 0 && (
                <div>
                  {h.excluded_trades} trade(s) worth {money(h.excluded_pnl, true)} are marked in the
                  bots&apos; record as not strategy trades. They are in the balance and on the
                  chart, and left out of the figures below.
                </div>
              )}
              {brokerMatches === false && (
                <div>
                  The rebuilt balance does not match MT5's live balance of{' '}
                  {money(brokerBalance, false)}. If a trade just closed, refresh in a minute;
                  otherwise a figure on this page is wrong.
                </div>
              )}
              {brokerMatches == null && !snapLoading && (
                <div>Could not check the rebuilt balance against MT5's live balance.</div>
              )}
              {(h.open_positions ?? 0) > 0 && (
                <div>
                  {h.open_positions} position(s) still open; their costs so far (
                  {money(h.open_position_costs, true)}) are in the balance and in no trade.
                </div>
              )}
              {(h.adjustments_total ?? 0) !== 0 && (
                <div>
                  {money(h.adjustments_total, true)} of broker charges or corrections moved the
                  balance without being a trade.
                </div>
              )}
              {(h.unmatched_plans ?? 0) > 0 && (
                <div>
                  {h.unmatched_plans} bot record(s) named a trade here but sat too far from its
                  entry to trust; those trades show no stop.
                </div>
              )}
              {h.bars_note && <div>Price bars: {h.bars_note}</div>}
            </div>
          )}

          <div className={cardCls}>
            <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
              <div className={headCls + ' mb-0'}>Balance</div>
              <div className="flex items-center gap-3 text-[11px] text-text-tertiary">
                <span>
                  <span
                    className="inline-block w-3 h-[2px] align-middle mr-1"
                    style={{ background: C.pos }}
                  />
                  Balance
                </span>
                <span>
                  <span
                    className="inline-block w-3 h-[2px] align-middle mr-1"
                    style={{ background: TWR_COLOR }}
                  />
                  Growth excl. deposits
                </span>
                <SeriesToggle label="Trade excursions" on={histOn} onChange={setHistOn} />
                <XModeToggle
                  value={xMode}
                  onChange={(next) => {
                    setXMode(next)
                    setXModePref(next)
                  }}
                />
              </div>
            </div>
            {points.length ? (
              <EquityCurveChart
                data={points}
                overlayLines={[
                  { id: 'twr_equity', color: TWR_COLOR, name: 'Growth excl. deposits' },
                ]}
                markers={markers}
                showHistogram={histOn}
                xMode={xMode}
                windowStart={h.flows[0]?.date ?? null}
                height={300}
              />
            ) : (
              <div className="text-[12px] text-text-tertiary">No closed trade yet.</div>
            )}
          </div>

          {points.length > 0 && (
            <PerformancePanel
              run={run}
              fallback={fallback}
              equity={book}
              balance={base > 0 ? base : null}
            />
          )}

          <div className={cardCls}>
            <div className={headCls}>
              Price{h.bars_server ? ` · bars from ${h.bars_server}` : ''}
            </div>
            <PriceChartView
              spec={h.chart ?? undefined}
              isLoading={false}
              isError={false}
              requestCandles={symbol ? requestCandles : undefined}
              height={520}
              isFullscreen={fullscreen}
              onFullscreenClose={() => setFullscreen(false)}
            />
            {!fullscreen && h.chart && h.chart.candles.length > 0 && (
              <button
                onClick={() => setFullscreen(true)}
                className="mt-2 text-[11px] text-text-tertiary hover:text-text-primary"
              >
                Full screen
              </button>
            )}
          </div>

          {points.length > 0 && (
            <div className={`${cardCls} space-y-8`}>
              <div>
                <div className={headCls}>Drawdown from peak (deposits and withdrawals removed)</div>
                <DrawdownChart equity={book} height={160} />
              </div>
              <div className="grid gap-6 lg:grid-cols-2">
                <div>
                  <div className={headCls}>Daily P&L</div>
                  <DailyPnlChart data={run.daily_pnl} netPnl={run.net_pnl} height={220} />
                </div>
                <div>
                  <div className={headCls}>R distribution</div>
                  <RDistribution points={scored} height={220} />
                </div>
              </div>
              <div>
                <div className={headCls}>Long vs Short</div>
                <DirectionBreakdown equity={book} />
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
