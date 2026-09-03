# Frontend Build Notes

**Status:** 📦 **ARCHIVE — relocated history, deliberately.** Same pattern as `BACKEND_BUILD_NOTES.md`: per-page detail moved OUT of `command-center/frontend/CLAUDE.md` so that file could stay conventions-only. Nothing here is current status.

Implementation-level detail for specific pages/components, relocated out of `command-center/frontend/CLAUDE.md` to keep that file to standing conventions and current status. Nothing here is deleted from the record — treat this as the detailed appendix. `CLAUDE.md` keeps a short current-state summary and a pointer here.

---

## BacktestDetail.tsx

Full run detail — full-bleed page (`-m-[22px]` cancels main's padding) laid out as a column: (1) a FULL-WIDTH header row (back link, title, chips, action buttons Rerun/Tune/Optimize/Stress Test) spanning the entire width; (2) below it a flex row that shares the remaining space between the collapsible left ParamsSidePanel (full-height bg-surface column flush against the nav sidebar, border-r divider; inner block sticky top-0 so params stay visible while scrolling; strategy-logic params + collapsible foundational; marks params changed vs baseline with strikethrough old→new for tune iterations; collapse persists in localStorage `bt_params_panel`; collapses to a thin vertical rail) and the detail content (flex-1, re-adds px/pb-[22px], reflows when the panel toggles): banners; an Evaluation + Performance block (`PerformancePanel`: a `VerdictRibbon` carrying the verdict, its rule chips and the trade-count anchor, over the three Made/Risked/Trusted cards; clicking through firms swaps the selected firm's sized numbers/charts in via `effRun` — an **optimizer combo** (`isOptCombo`: has `optimization_id`, no equity curve, complete) swaps in an `UnscoredRibbon` with a **Run Full Backtest** CTA instead of a verdict, and a run with no evaluations gets a ribbon carrying only the trade count. Every path renders the same three cards, so there is no longer a separate full-width layout. Running a full backtest on a combo with no inheritable ruleset opens `FullBacktestEvalModal` (market-aware ruleset picker — forex for MT5, futures for NT8) — driven by the backend's `status: "needs_ruleset"` reply; the choice re-fires via `useRetryBacktest({ runId, evaluateRulesets })`); tabbed charts (Equity/Price/Breakdown — Breakdown holds Drawdown + Daily P&L + Long-Short together; each panel fullscreen-expandable via ChartModal) + permanent Performance by Regime; logs. The account-balance slider now lives in the ParamsSidePanel footer.

### Chart and KPI conventions

- Charts: one **tabbed panel** — **Equity / Price / Breakdown** (shared `ChartTabPanel` draws the tab chrome). Equity & Price are the big ~520px charts (Price lazy-loads its ChartSpec via `PriceChartPanel`). The **Breakdown** tab stacks all three supporting charts together (Drawdown full-width on top, then Daily P&L + Long/Short side by side) sized to share the tab height. Every panel has an **Expand** button (`Maximize2`) → a portalled full-screen `ChartModal` (Esc / backdrop / X to close) that re-renders the active tab at the measured viewport height — fullscreening Breakdown blows up all three together. A `renderChart(key, h)` helper draws each chart at a given height for both inline and fullscreen. **Performance by Regime** is a permanent table below. Regime context shows as **faint background bands** on both the Equity and Sized-account views (`ReferenceArea`, fillOpacity 0.1 — NOT line-segment colors), toggled by a `RegimeOverlayToggle` shown on either tab (shared on/off state); same treatment as the tune page. The equity draw animation is kept (and the Sized account chart matches it); the `ChartModal` overlay uses a **solid** `bg-bg-base` (NOT `backdrop-blur`) — blurring the whole viewport is recomputed every animation frame and made the fullscreen line render choppy.
- **KPIs (`PerformancePanel`, rebuilt 2026-07-31): a verdict ribbon over three question cards.** Replaced the 6+6 `KpiGrid` + `EvalCard` two-column layout, which produced all three of the standing complaints at once — cropped values, uneven cards, and an empty evaluation box — none of them fixable by resizing, because each was a consequence of the layout. Metrics group by the question they answer: **Made** (hero = return multiple `(balance + net) / balance`, falling back to net P&L; rows Net · Per trade · Avg win/loss · Win rate · Profit factor), **Risked** (hero = peak-relative max drawdown + `DrawdownMeter`; rows Deepest drop · Worst day · Worst streak · Time underwater), **Trusted** (hero = Calmar; rows Profit concentration · Sharpe · Z-score · Avg hold). Deleted with it: `KPI_ROW_H`/`KPI_ROW_H_EXPANDED` (a constant height on variable content — the actual cropping mechanism), `KPI_COLS` (`1.4fr repeat(5,1fr)`, widened once for a long money value and visibly lopsided ever after), `KPI_TONE_BORDER`, `MoreMetricsToggle` + `showMoreKpis`, `TradeCountStandout`, `EvalCard`/`UnscoredEvalCard`/`EvalRow`, and `useIsLg` in both pages. Three cards hold every metric at once, so nothing hides behind a chevron and rows flow rather than clip. `deriveKpis` is unchanged and still the single derivation feeding the news filter's `compare`. `StackDetail` renders the same panel, passing `StackTradesRibbon` into the `ribbon` slot.
- **The evaluation card became the ribbon** (`VerdictRibbon`). A row costs no vertical space when a ruleset has little to say and grows a `RuleChip` per rule when it has a lot, so `unconstrained` — which states no rules by design — can no longer render 300×196px of nothing. `INFO` shows as a neutral **Not graded** chip with a line explaining that nothing was checked (see `backend/CLAUDE.md` → *Nothing checked is not a pass*); an optimizer combo swaps in `UnscoredRibbon` with the Run Full Backtest CTA. The `unfiltered` verdict badge moved here from the old column header. **Trade count is the ribbon's anchor** (`TradeCountAnchor`, 29px, right-hand divided zone) with span + cadence beneath it (`5.5 yrs · ≈2/month`) — it is the sample size every other number rests on, and cadence is the unit the root `CLAUDE.md` Trading Philosophy states the target in.
- **Colour marks the exception, not the sign.** Only the three heroes, every delta (both directions), and rows that cross a threshold get colour — roughly four coloured things per screen instead of twelve. Sign-colouring fails three ways: on a working strategy nearly every row is positive so green ranks nothing; Worst Day / Deepest in $ can only ever be negative so red is decoration on a definition; and Sharpe 0.91 is positive AND weak (this run's own news filter moves it 0.91 → 2.98 on 3 of 142 trades). Soft numbers say so in words via the existing `sharpeLabel` / `zScoreLabel` / `concentrationLabel`, which since 2026-07-31 end the row's TOOLTIP rather than trailing the value. Sharpe additionally goes **amber below 1.0** — not a sign colour but the same exception rule, since 0.91 is the value green would have called good. `exceptionCls(cls)` maps `text-text-primary`/`text-text-tertiary` to `undefined`, so the surviving `*Cls` helpers stay the single definition of "bad" while only crossings get painted. Worst streak is the one hand-written threshold (≥6 — 3 losses in a row is ordinary on a selective strategy and colouring it would spend the amber before a real streak arrived).
- **`DrawdownMeter` may never invent a reference.** 54.9% is neither good nor bad without one, but both are drawn only when real: the **gold limit tick** from `ev.personal_max_drawdown_from_peak_pct` (prop rulesets cap a trailing DOLLAR floor — a different rule — so they get no tick and show ribbon chips instead; never convert one to the other), and the **hatched tail** from the stress test's `pct1_max_dd_pct`, gated on `dd_basis === 'percent'`. With no stress test the caption reads "the simulated tail is unknown, not zero". The track snaps to `METER_CEILINGS` (25/50/75/100) rather than scaling per run, so two runs of a strategy stay comparable.
- **Time underwater** (`computeTimeUnderwater`): share of the test's CALENDAR span below the previous equity high, rebased to 0 so it never depends on the balance. Max drawdown says how deep the hole was; this says how long you sat in it, which is the half that decides whether a strategy is holdable. Weighted by elapsed days, not by row count (fixed 2026-07-31) — `daily_pnl` holds only days that closed a trade, so counting rows answered "what share of ACTIVE days" while the label said "of days", and on a strategy trading ~2x a month one row is worth two weeks. On the shipped `mpc_sos_fade` run: 67% by rows, **71% by the clock**.
- Folded-in metrics (no separate card): Recovery Factor → Calmar's tooltip. Avg win/loss R:R got its own **Made** row on 2026-07-31 (it had been riding as a suffix on Per trade, which is a different metric). The DEEPEST dollar drawdown is the **Deepest drop** row — renamed off "prop-firm view" the same day, since it is the deepest fall on any account and the prop framing meant nothing on a forex personal ruleset; its tooltip says the thing that actually matters, that on a compounding run it is a DIFFERENT episode from the percentage above it.
- **A row is a label, a ⓘ and a number — nothing else (2026-07-31).** `PanelRow.tip` is required and carries both the definition and what this run's value means; the `*Label` helpers now end a tooltip instead of trailing a value. Row suffixes cost twice — they re-explain a term the reader learned on first read (`4 days · consecutive losing`), and they make the value column ragged, since a column of numbers is only as tidy as its longest sentence. `PanelRow.value` is a **string** and must not use `FitMoney`: that component measures a flex cell which shrinks to its content, so it abbreviated Net to `+$846.3k` in a card wide enough for `+$846,257` twice over (it stays on the fixed-width hero). The delta is the one thing still allowed beside a value. Units are converted rather than printed raw — `fmtHold` turns `1365 min` into `22.8 h`. `InfoTip`'s icon went 9px/50% → 11px/full tertiary in the same pass: nobody hovers what they can't see.
- **The panel collapses to its heroes (2026-07-31).** Chevron on the `PerformanceHeader`, `collapsed` prop, persisted under `performance_panel_collapsed`, **default ON** — hence `getPerfCollapsed` rather than `getBoolPref`, which defaults off. Expanded, the panel plus header fills the fold on a laptop and pushes the equity curve off screen, and the two are read together. The heroes and the drawdown meter survive the collapse. **Measured at 1670×900 with the params panel collapsed: 234px collapsed / 359px expanded, down from 318 / 496** (~27% in both states). The four cuts: the card's question shares the title's line (its own row charged ~16px per card for a sentence nobody re-reads); the meter's limit-label padding is charged only when a limit exists (15px of blank card otherwise); the ungraded ribbon sentence is short enough to share line one with the chips (the long form wrapped and pushed `TradeCountAnchor` to a second row — ~35px in BOTH states, and invisible in the source); and rows are `py-[4px] leading-[1.3]`, 24px each. Measure on a real render before trimming; three of the four were not where the source suggested.
- **Three metrics were saying the wrong thing (fixed 2026-07-31).** All unit/basis errors, all plausible enough to survive a redesign. (1) `worst_losing_streak` counts **trades**, not days — `backtest/output.py:_worst_losing_streak` walks the trade list, and "4 days" read as a far worse run of luck than the real 2 consecutive losing calendar days. (2) Time underwater, above. (3) Profit concentration, below. Also: **`fmtDate` parsed `'YYYY-MM-DD'` as UTC midnight** and printed it in the viewer's timezone, so the run header read `Jan 1, 2021 → Jul 27, 2026` for a run stored as `2021-01-02 → 2026-07-28`. Five pages carried their own copy of that function and all five were wrong (`BacktestDetail`, `SweepDetail`, `OptimizationDetail`, `StackDetail`, `StressTestDetail`); `chartDateLabel` in the same file already had the `T00:00:00` guard.
- **Profit concentration measures the EDGE, not the account (2026-07-31).** `computeProfitConcentration` weights each trade by its RETURN on the equity it was taken with, whenever the run compounded. In dollars the metric reports the compounding rather than the clustering it exists to detect: on an account that grows 85x the last quarter must hold nearly all the dollars however evenly the edge is spread. On `d2ab68f9e884` the dollar quarters $9k / $49k / $71k / $1,039k read **89%** and printed the panel's only warning colour ("edge clustered — overfit risk"); the same trades as returns read **40%** ("spread across the test"). The switch is `equityBase(equity) > 0` — an NT8-shaped cum-P&L-from-zero curve is a unit-size run whose dollars ARE already comparable, and dividing those by a fictitious balance would introduce the opposite bias. The panel computes this client-side rather than reading `run.profit_concentration_pct`, because the stored column is whatever basis was current when a run FINISHED; `services/metrics.profit_concentration_pct` applies the identical rule and `init_db` re-stamps history.
- **Max Drawdown is PEAK-RELATIVE (2026-07-30).** The card's value is `maxDrawdownPctOf(rebaseEquity(equity, balance))` — the worst drop as a fraction of the equity it fell FROM. It used to be the deepest DOLLAR drawdown over the ruleset's static `account_size`, which on a compounding run reported a percentage that never happened: the shipped `mpc_sos_fade` run read **1096.7%** because a $109,665 drop off a $330,303 peak was divided by a $10,000 balance the account had grown 33x away from. Honest value: **54.9%**. The same defect the stress-test engine fixed the same day on the Monte Carlo side (`backend/CLAUDE.md` → *dd_basis*), in a second file. **The biggest DOLLAR drawdown and the biggest PERCENTAGE drawdown are different EPISODES on a compounding run** ($109,665 = 33.2% late; the 54.9% was only $9,198 in Nov 2022), so `maxDrawdownPctOf` returns the dollars and peak of the episode it measured and the sub-line prints those (`−$9,198 from a $16,748 peak`). Printing the deepest dollar figure beside the percentage would be a new lie in place of the old one; it lives in the **Deepest drop** row instead, whose tooltip states plainly that the two are different episodes.
- **Calmar divides by that same peak-relative fraction.** Both sides must compound — CAGR always did. Against a static balance it read **0.11 (red, "poor")** on a run whose honest value is **2.25**. Consequence to keep straight: Calmar **does** move with the Account balance slider now (both halves depend on the balance and do not cancel) — the old "capital-independent by design" note was wrong and is retired.
- **Account-balance what-if slider lives in the `ParamsSidePanel` footer** ("Account balance · rebases Max DD %"). `PerformancePanel` takes `balance` (for the calc only); `ParamsSidePanel` takes `balance` / `defaultBalance` / `onBalanceChange` and renders the slider. It now moves THREE heroes, not two — Made's return multiple joined Risked's drawdown % and Trusted's Calmar. All are trade-derived and identical across NT8/MT5; every other metric comes from the trades, not the balance.
- **Avg Trade** (duration) is **blank ("—") for MT5 runs** — the MT5 Strategy Tester report carries only trade-close times (no entry time), so duration can't be computed (`algos/.../mt5_agent.py`, off-limits + would need a VPS redeploy). The card's sub reads "duration unavailable" in that case so it doesn't look broken. **Net P&L** carries a sub (return % of balance, else "net of commissions") so it lines up with the other cards (every KPI card reserves the sub line's height).
- Sharpe shows the **canonical daily-√252** value, with the platform value + `low sample` flag in its tooltip, and prefers the backend-persisted `run.platform_sharpe`. Profit Concentration no longer prefers `run.profit_concentration_pct` — see the return-basis note above.
- Verdict colours: `VERDICT_CHIP` maps `PASS`/`WARN`/`DISCARD`/`INFO`. Personal/demo runs get **real PASS/DISCARD verdicts** with their own chips (drawdown-from-peak + consecutive-capped-days, keyed on `ev.ruleset_type`, never on the `firm_max_loss_eod = 0` sentinel — that value must never render, incl. drawdown-chart limit lines). **`INFO` renders as "Not graded"** — neutral, no rule chips, plus the line saying nothing was checked. It covers both pre-evaluator-pass rows and (since 2026-07-31) any ruleset stating no fail condition, which used to return a green PASS. `StrategyDetail`'s `VERDICT_PILL_STYLE` also maps INFO to a neutral style; `Backtests` ChallengePills are verdict-agnostic (coloured by ruleset). Ribbon rail override: when `verdict === 'DISCARD'` but `net_pnl > 0`, the left rail goes amber but the chip keeps the DISCARD label/icon.
- Header chips: instrument = `font-semibold font-mono bg-accent/10 text-accent border border-accent/20`; date = `font-medium font-mono bg-bg-surface border border-border-subtle text-text-secondary`; ruleset = `font-semibold font-mono bg-warn-muted border border-warn-text/20 text-warn-text`
- WorthinessBadge removed from BacktestDetail header — verdict lives in the `VerdictRibbon` only
- StatusBadge only rendered while the run is actively `running` — not shown for `complete` (implied by being on the detail page)
- Drawdown chart shows firm limit reference lines from evaluations
- Calendar-based x-axis ticks (start, quarterly, end) — not interval-based
- Long vs Short section uses donut pie charts (Recharts `PieChart`/`Pie`/`Label`): won (green) vs lost (red) slices, win rate % as center label. Won label on right (matches green arc), lost label on left.
- All chart tooltips: `contentStyle={{ background: C.tooltipBg, border: '1px solid ${C.tooltipBorder}', borderRadius: 8, fontSize: 13, padding: '8px 12px' }}`, `labelStyle={{ color: C.axisTick }}`, `itemStyle={{ color: '#e5e7eb' }}`. Never use `C.tooltipBorder` as text color — it's a dark border hex, not readable text.
- Equity curve custom tooltip: uses `content` prop (not `formatter`/`labelFormatter`) to filter out `_s0..N` segment keys from the payload — only the `equity` entry is shown. It also surfaces the trade's **Favorable / Adverse excursion** (`EquityPoint.favorable`/`adverse`) whenever the point carries them.
- **Equity curve TradingView-style panel** (`EquityCurveChart`, a `ComposedChart`): the cumulative-PnL line is **colour-split at the STARTING BALANCE** — green above it, red below — via two `linearGradient`s (`eqStroke`, `eqFillSplit`) that hard-stop at `startOffset`. **`startEq` is the opening balance, NOT `data[0].equity`**: the curve is anchored on the opening balance and the first point already includes trade #1's P&L, so `startEq = data[0].equity - data[0].profit` (works across runners — NT8 anchors at 0, MT5's first point has no profit). **`startOffset` maps to the FILLED SHAPE's bbox (data extremes incl. startEq: `(dMax - startEq)/(dMax - dMin)`), NOT the padded axis domain** — using the padded domain drifted the boundary off the start line and bled a faint red tint into the positive region. The dashed break-even `ReferenceLine` sits on this line. The **Y axis is tick-anchored ON `startEq`** (`yTicks` walk out from it by a `niceStep`) so the starting balance is always labelled; ticks read as balances (no "+" prefix). The curve is **anchored** on the starting balance: a synthetic `{index: firstIdx-1, equity: startEq, _anchor: true}` point is prepended to `chartData` so the line leaves the `startEq` line at the axis instead of jumping in at trade #1's balance (the anchor draws no dot/bar and its tooltip just reads "Starting balance"). A **dot on every trade point** (custom `dot` fn) is coloured green/red by above/below `startEq`; the **`activeDot` is a matching render fn** (a fixed colour showed green even on underwater points). Hover shows Balance, this-trade P&L, and (when present) Favorable/Adverse excursion. The **XAxis is `scale="point"` with `padding={{left:0,right:0}}`** — a bar series otherwise flips it to a band scale that pads both sides and shifts the whole curve right, opening a gap at the y-axis.

Two opt-in `SeriesToggle`s (equity tab, `localStorage`-persisted):
- **Bottom-bar toggle** — ONE toggle, label `Trade excursions` when the run carries excursion data else `Histogram`. Without excursion it draws plain per-trade `profit` bars (green/red `Cell`s, `fillOpacity 0.35`) on `yAxisId="bars"` (domain `[-barMax, 6×barMax]`). With excursion it draws the **combined TradingView-style bar** via a custom `shape` on `yAxisId="exc"`: translucent green halo up to favorable, translucent red halo down to adverse, and a solid net-result core (opacity 0.6) between. It's drawn **in true dollars anchored on the `startEq` line** — the `exc` axis is the balance axis *shifted* so its zero sits on `startEq` (`domain=[yMin-startEq, yMax-startEq]`), and the hidden bar's own pixel height gives the `$-per-pixel` ruler (`ppd = height/scale`, `scale = max(fav, -adv)`) the shape uses to place favorable/adverse/net. Do NOT use `baseValue` on a `Bar` (Area-only prop) — the shifted axis is how the baseline lands on `startEq`.
- **Run-ups & drawdowns** — a thin green/red ribbon along the very bottom (`ReferenceArea` per segment, `y1=yMin`, `y2=yMin+2.5%`). `computeRunupDrawdownBands` marks each point run-up (green, equity ≥ running peak) or drawdown (red); the first segment's `x1` is pulled to the anchor so the ribbon spans the full axis.

Bars size to the category width (`maxBarSize 28`, Recharts' ~10% gap) so they're responsive — thicker with fewer trades, thinner with more; the excursion shape fills the full slot (`w = width`). The equity line is `strokeWidth 2.5` and bar cores are muted to `0.6` so the line reads clearly on top of same-colour bars. Regime `ReferenceArea` bands **skip UNKNOWN** so the chart matches the legend exactly. Colour split + histogram + run-ups need no re-run; excursion needs the `favorable`/`adverse` fields (`models.EquityPoint` must declare them or FastAPI drops them; `backtest/output.py` fills them from `execution.Trade.mfe_usd`/`mae_usd`), so pre-existing runs must be re-run once.
- **Price chart** (separate from the Recharts analytics above): a lazy-mounted `<PriceChartSection>` renders the klinecharts candlestick panel (`components/ChartPanel/`). It is collapsed by default and only fetches the run's ChartSpec (`useChartSpec`, served by `GET /backtests/runs/{id}/chart-spec`) when opened — the candle fetch is heavy. Falls back to a daily-candle note when intraday history is unavailable. See `components/ChartPanel/CLAUDE.md`.

---

## TuningWorkbench.tsx

Route `/backtests/runs/:runId/tune` — param editor seeded from a baseline run, runs tweak iterations (`source_run_id=baseline`), leaderboard with deltas, regime-aware cumulative-P&L overlay, net-P&L-by-regime table. Live progress for the running iteration via `useLabProgress` (watch in-place; no need to leave).

**Layout:** chart + leaderboard are the hero; the shared `ParamEditor` lives in a full-height **dockable left side panel** (mirrors BacktestDetail's `ParamsSidePanel` pattern — `-m-[22px]` full-bleed root, sticky inner, `panelCollapsed` → thin rail, persists `tune_params_panel` in localStorage). The editor runs in `explainer="coach"` mode: rows never shift as focus moves; instead a pinned **`<ParamCoach>` strip** sits at the bottom of the dock (above the Run-iteration footer) showing the focused param's name/current-value/`default`/desc + ↓Lower/↑Higher guide (numbers) or named states (toggles), driven by `onFocusChange`→`coachParam`. The cumulative-P&L overlay (`renderOverlay(h)`) is the visual hero (~440px) with an Expand button → fullscreen modal (Esc/✕ to close).

**Cross-linking:** tune iterations are NEVER top-level Runs rows — they nest under their baseline (`TuneNestRow`) when it's a visible row, otherwise (e.g. tuned from an optimization winner) they live only in the workbench. In-progress indicators (presence only, never a count, shown on ONE row not both): in the Runs tab the pulsing "TUNING" chip lives on the `OptimizationNestRow` whose winner has a running tune (driven by `runningTuneSourceRuns`) — NOT also on the parent `RunRow`; a direct tune of a standalone run shows via its `TuneNestRow` "Running" status. On `OptimizationDetail` the indicator is a "TUNING WINNER" chip in the Results header (kept out of the table so it doesn't widen columns) + the "Tune winner" button becomes "Tuning…" with a spinner. Reached via: those rows, the "Tune winner" button, and BacktestDetail's "Tuning iteration → workbench/optimization" breadcrumb (runs with `source_run_id`). The Runs-tab single-run progress banner is suppressed when the running job is a tune (no orphan indicator).

---

## StressTestDetail.tsx

Laid out as a CONTEXT ROW + a unified tabbed ANALYSIS WORKSPACE. Context row (2 cols, side by side): the grade card (coloured grade strip + name + ruleset chip + three `VerdictTile`s — the headline KPI from each analysis so the whole test reads at a glance: Monte Carlo breach %, Walk-Forward degradation, Sensitivity worst-case, each graded robust/acceptable/fragile) and the source backtest card (links back to the run via `useBacktestRun`). Delete lives top-right in the header row (labelled "Delete" button, mirrors `OptimizationDetail`).

Below: ONE `ChartTabPanel` (Monte Carlo / Walk-Forward / Sensitivity) where each tab renders its own KPI cards (`aboveChart`) directly above its own chart, so KPIs and chart always match. MC tab = 6 cards (4 MC stats + `ProbCard` breach + pass) above a tall Equity Path Fan (the hero, ~⅔ height) + a smaller Max Drawdown Distribution; WF tab = degradation/avg-IS/avg-OOS/windows above the IS-vs-OOS bars; Sens tab = worst-case/most-fragile-param/params-tested/median-change above the tornado bars. Per-tab fullscreen via `ChartModal`.

`gradeWord()` grades a ratio → `{pct, word, cls}`; thresholds: MC breach 5/20, WF degradation 20/30, sensitivity 25/40. The dollar drawdown limit threaded to cards/charts is `ddLimit` — mirrors backend `effective_dd_limit_usd` (personal/demo = account_size × %-from-peak; prop = max_loss_eod), so personal rows never render a $0 limit. Prob-pass card label is ruleset-aware (personal: "Prob. Stay Safe").

---

## Other page-level implementation notes (Backtests, StrategyDetail, Rulesets, Optimizations, StressTests)

**Backtests.tsx** — lab landing — Runs / Sweeps tabs (URL-based). Exports shared `ConfirmDeleteModal`, `RunsTableSkeleton`, `fmtOptStatus`. Sweep child runs are NEVER flat top-level Runs rows (filtered by `!r.sweep_id`, same as optimization combos): a UI-created sweep nests under its origin run via `SweepNestRow`; a standalone/legacy sweep (no `source_run_id`) lives only in the Sweeps tab. Runs table has no Status column (the count was redundant with the tab badge too, so it's gone): status shows as a small `RunStatusIcon` after the strategy name (pulsing accent dot = running, red ✕ = failed, green dot = complete — done is otherwise implied by populated metrics). Column order is `… Score · Trades · Net P&L · Max DD · Win% · Challenge · Duration` (Trades = `run.trade_count`, right after Score; Duration last). Duration uses `run.started_at ?? run.created_at` → `completed_at` so a retried run counts only the latest attempt, not back to the first kickoff. A collapsible `WorthinessLegend` ("Score key") sits above the table. The Runs filters (market All/Futures/Forex, status select, Refresh) render on the tab row itself, right-aligned via TabBar's `right` slot — `statusFilter`/`marketFilter` are lifted to the page shell; Refresh just re-fetches `['lab','runs']` (the list also auto-polls, so it's a manual override, not the only way to update). Market is derived from `run.runner` (`mt5` = forex, else futures) via `runMarket()` — NOT the instrument name, which mis-bucketed broker-suffixed forex (`GBPJPY.s`) and futures months (`MYM 06-26`).

**StrategyDetail.tsx** — strategy "spec sheet" — full-width header (labeled Type/Runs-on/Market/Parameters chips) + Overview card (editable description "What it does", optional flow `steps`, optional "The edge" — both from `<Strategy>.meta.json` top-level `steps`/`edge`), then a two-column body: sticky LEFT side panel (Jump-to-group nav, ★ Essentials at-a-glance, Backtest-runs summary + deep-link to `/backtests?tab=runs&market=forex|futures`) and RIGHT collapsible grouped param tables (Parameter · What it does · Default+unit · Tuning effect from `guide`; no raw types; ★ on `core`; `show_if` → "only when" chip; toolbar: Essentials-only / Expand-all / Collapse-all). Column tops are kept inline via equal-height `ColHead`s. No pre-deployment checklist (removed — it was a prop-eval concept that didn't map to a strategy).

**Optimizations.tsx** — OWN top-level page (route `/optimizations`, Lab group) — optimization list table. Decoupled from the Backtests tab. Count shown as a pill beside the title (not a "N optimizations" text label); checkbox multi-select bulk delete (matches the Backtests pattern: select-all header checkbox + per-row, "Delete N" button by the count, `ConfirmDeleteModal`, `Promise.allSettled` over `DELETE /optimizations/{id}`). Running optimizations are not selectable (cancel first).

**StressTests.tsx** — stress test list — grade badge, strategy/instrument/status columns, prob breach/pass, created. Count shown as a pill beside the title (not a text label); a collapsible `GradeLegend` above the table; checkbox multi-select bulk delete (matches the Backtests pattern: select-all header checkbox + per-row, "Delete N" button by the count, `ConfirmDeleteModal`, `Promise.allSettled` over `DELETE /stress-tests/{id}`).

**Rulesets page** (`pages/Rulesets.tsx`, route `/rulesets`, Reference group, with Calendar; old `/strategies?tab=rulesets` links redirect). Prop rows grouped by FIRM name (`FIRM_BRAND_NAMES`: Lucid / Tradeify / FundedNext / Apex — "LucidFlex" is Lucid's PROGRAM, not the firm); row names carry only the program/challenge (e.g. "Select $50k Evaluation" under TRADEIFY) — canonical names live in `lab_db._RULESET_DISPLAY_NAMES`, applied every `init_db`. The filter row is page-level: All / each firm / Personal — a firm chip shows only that firm, Personal shows only the personal group. Prop table columns: Name / Type / Account Size / Profit Target / Max DD (EOD) / Consistency / Min Days / Contracts (`Min Days` = `min_trading_days`, the eval-pass minimum — "—" when the firm publishes none; verified 2026-06 against firm docs: LucidFlex/FundedNext-Flex/Apex-EOD = none, Tradeify Select eval = 3 from its 40% consistency rule). Personal/demo rows show Daily Cap / Daily Target / Max DD from Peak / Max Loss Days (no Min Days — not a personal-account concept). Both tables end with a Contracts column (`ContractsCell`): fixed caps as `N mini / M micro`, scaling rows add a gold SCALES pill, FundedNext rows add a cyan MIX pill (minis+micros share one cap at 1:10; excess profit voided). SCALES and MIX both use CSS hover tooltips (never the native `title` attr — unreliable) anchored `right-0` so they grow INTO the table — the wrapper is `overflow-hidden`, so a left-anchored tooltip in the last column gets cropped. Personal rows show a dash. **Editing:** personal/demo rows get a pencil → `PersonalRulesEditModal` (5 fields: account_size, daily_loss_cap, daily_profit_target, max_drawdown_from_peak_pct, max_consecutive_loss_days) saving via `usePatchPersonalRuleset` → `PATCH /rulesets/{id}`. Prop rows show a lock icon ("Firm rules — not editable") and no edit affordance — the real lock is server-side: PATCH and PUT both return 403 for prop rows, and PATCH rejects non-allowlisted fields 422. `FoundationalEditModal` was removed with the lock; foundational values on personal rows are still editable via the PUT endpoint (no UI affordance currently).

---

## Sizing UI implementation detail (RunBacktestModal, BacktestDetail)

`ParamSchemaEntry` carries `category?: 'strategy_logic' | 'foundational'`. Foundational params are never shown as editable inputs in `RunBacktestModal` or the optimizer grid — both filter them out. Instead, `RunBacktestModal` shows a readonly "Foundational Config" section (10 values pulled from the primary ruleset) once a firm is selected, and pre-fills commission/slippage from that ruleset's defaults. The `Ruleset` type holds all 10 foundational fields (`risk_per_trade_pct`, `max_consecutive_losses`, `earliest_entry_time_et`, `latest_entry_time_et`, `days_of_week_allowed`, `daily_profit_target`, `daily_profit_lock_pct`, `default_commission_per_side`, `default_slippage_ticks`, `daily_halt_fraction`) plus the 2 personal fail-condition fields (`max_drawdown_from_peak_pct`, `max_consecutive_loss_days`).

`RunBacktestModal`'s `ParamInput` must render strategy-logic params **by `ParamSchemaEntry.type`**: `bool`→checkbox, `string`→text input, everything else→numeric (`type="number"`). The `string` branch is required — without it, string params (e.g. LondonBreakout's GMT session-window times `"00:00"`, MeanReversion's session-hours strings) fall through to the numeric input, which can't display a non-numeric value and renders **blank**, and `parseFloat` would corrupt it on edit. The scanner extracts string defaults correctly (`raw_val.strip('"')`), so a blank field is always a render-type bug, not a missing default.

`RunBacktestModal` also carries a **Sizing Mode** toggle (`sizingMode` state, Consistent | Bullet, default consistent) above "Evaluate Against", sent as `BacktestRunRequest.sizing_mode`. It picks how the dynamic sizing engine turns the strategy's unit-size signals into real contracts (consistent = room÷7 per trade; bullet = max the firm's ladder allows) — it only affects strategies reshaped for the engine (ORB) and is inert for the rest. Backend stores it on `backtest_runs.sizing_mode` and reads it back at completion. `BacktestDetail` then carries `sizing_mode` + `sized` (bool) + `sized_timeline` (`SizedTimelineDay[]`, the engine's day-by-day record); the detail page renders an accent **"Engine-sized · Consistent/Bullet"** pill in both header layouts (full + condensed sticky), shown only when `run.sized` — invisible on every current unit-size run.

**Sized equity curve (chart tab).** When `run.sized && run.sized_timeline.length`, the BacktestDetail chart panel inserts a **Sized account** tab (between Equity and Price) AND relabels the plain **Equity** tab to **Strategy (1 unit)** so the hierarchy reads: one is the bare strategy at flat 1 unit (the raw edge — is there one at all?), the other is the real account under the ruleset. The relabel + the Equity subtitle change are gated on `hasSized`, so every unit-size run keeps the plain "Equity" label. `SizedEquityCurveChart` (Recharts `ComposedChart`) plots the REAL sized account day by day: an area for **end-of-day balance** (green/red by net) and a red dashed **stepAfter** line for the **trailing risk floor** (`risk_floor` — the firm's max-loss line). The gap is the buffer; balance crossing the floor is a breach (red `ReferenceDot`); halt days are gold `ReferenceDot`s; the per-day tooltip shows balance / floor / buffer / trades / contracts / halt reason. `SizedCurveLegend` below names the two lines + the sizing mode, and colors the balance swatch by `profitable` (matches the line — red on a losing account). The balance area + floor line use the same **left-to-right draw animation** (`animationDuration={1500}`) as the Equity curve. The tab is fullscreen-expandable like the others (`renderChart` `case 'sized'`; `primaryTab` union includes `'sized'`). Inert for every unit-size run (tab never appears). **Regime overlay** works on this tab too: the shared `RegimeOverlayToggle` shows on both Equity and Sized, driving faint background `ReferenceArea` bands + a `RegimeLegend`. Because the sized chart is indexed by day-position (`i`), not the equity curve's trade index, it uses its own `computeSizedRegimeBands(sized_timeline, daily_pnl)` → `sizedRegimeBands` memo (the equity `computeRegimeBands` bands would map to the wrong X domain).

**Sizing Timeline table.** Below the charts (next to Performance by Regime), `SizedTimelineTable` renders the engine's day-by-day audit from `run.sized_timeline` — Date · Trades · Contracts · Day P&L · EOD Balance · Risk Floor · Buffer · Status. Halt days tint gold, breach days (balance < floor) tint red with a Breach badge; the footer sums to the run's final balance / net P&L. Collapsible (default collapsed — a sized run can be hundreds of days) with a sticky header and a `max-h-[480px]` scroll body. Gated on `hasSized` like the Sized tab.

**Breach cutoff + banner.** A breached account is dead — the engine stops trading it — but the sized timeline still carries a frozen balance to the end of the requested range, which drew a long flat line to the far date and padded the timeline table with hundreds of no-trade rows. `trimToLastActive(timeline)` (applied inside `effRun` to `sized_timeline`, and its cutoff date filters `daily_pnl`) ends the sized view at the last day that actually traded, so the Sized chart, Sizing Timeline table AND Daily P&L bars all stop at the breach — matching the Drawdown/Long-Short charts, which already end there because they read `equity_curve` (only taken trades). Trimming `daily_pnl` also keeps dead post-breach flat days out of the daily-derived KPIs (worst day / streak / Sharpe / concentration). `breachInfo` (`selectedEval.drawdown_pass === false` → first day `eod_balance < risk_floor`) drives a red `AlertTriangle` **breach banner** rendered at the top of the Sized and Breakdown tabs ("{firm} breached its drawdown limit on {date}… charts end at the breach"), and the Sized/Breakdown subtitles name the selected firm — so the page explains its own cutoff instead of just looking truncated. Nothing renders for firms that didn't breach.

**Per-firm switching (`effRun`).** The strategy makes the SAME signals for every firm — but each firm's contract ladder/floor sizes them differently AND skips different trades on halt/breach days, so every firm has its own dollar P&L, sized daily P&L, sized timeline AND sized trade-by-trade equity curve. The backend persists all of them per firm (`EvaluationDetail.net_pnl` / `max_drawdown` / `profit_factor` / `win_rate` / `trade_count` / `avg_win` / `avg_loss` + `daily_pnl` + `sized_timeline` + `equity_curve`, from `ruleset_sizing.json` — see backend CLAUDE.md "Dynamic sizing & risk engine"). Clicking through the eval cards (`selectedEvalIdx` → `selectedEval`) builds `effRun` — a shallow copy of `run` with the selected firm's sized fields swapped in (including `equity_curve`; and the daily-P&L-derived metrics — `worst_day_pnl` / `worst_losing_streak` / `sharpe` / `platform_sharpe` / `profit_concentration_pct` — nulled so `PerformancePanel` + `fallback` recompute them from THIS firm's `daily_pnl`). `effRun` drives **everything ruleset-dependent**: the `PerformancePanel` (incl. the equity-derived Calmar / Max DD % / Z-Score via `equity={effRun.equity_curve}`), the ribbon's rule chips, the **Sized account** chart, the **Daily P&L** + **Drawdown** + **Long-vs-Short** breakdown charts, the **Sizing Timeline** table, `sizedRegimeBands`, and the drawdown **limit line** (the selected firm's `firm_max_loss_eod`). **`effRun === run` (no swap) when the selected eval has no `net_pnl`** — i.e. every unit-size run and every pre-2026-06-30 sized run (no `ruleset_sizing.json` on disk) — so nothing regresses; the headline is the fallback. **What deliberately stays firm-independent:** only the **Strategy (1 unit)** equity tab + its `regimeBands` and the Price chart (the bare 1-unit strategy / raw market — `run.equity_curve`, same for all firms by design).

---

## Key UI decisions — implementation detail

**Platform-based job lock** — `GET /backtests/running-job` returns `{ nt8: RunningJobInfo, mt5: RunningJobInfo }` (polled at 5s via `useRunningVpsJob()`). NT8 and MT5 lock independently. `jobBlocked = isMt5 ? !!runningJob?.mt5?.running : !!runningJob?.nt8?.running`. Lock surfaces: `RunBacktestModal`, `OptimizeButton`, `Tier3WarningModal`, `RunRow` retry, `BacktestDetail` retry/rerun. `Strategies.tsx` calls `useRunningVpsJob()` at page level (result unused) to keep the cache warm — without this, the first modal render sees `runningJob = undefined` and treats the lock as clear. All six job-lifecycle mutations invalidate `['lab', 'running-job']` on success. `BacktestSummary.runner` must be mapped in `_row_to_summary` or `run.runner` is undefined on the frontend. The backend `get_running_job()` correctly routes MT5 optimizations to the `mt5` bucket (joins `strategies` on runner) — a running MT5 optimization does NOT set `nt8.running`.

**Optimization running indicator** — `OptimizationNestRow` shows a pulsing gold dot (`w-[6px] h-[6px] rounded-full bg-gold-text animate-pulse`) when `opt.status === 'running'`. The parent `RunRow` does NOT show an "OPTIMIZING" badge — the dot on the sub-row is the only running indicator. MT5 optimizations emit live `completed_count`/`total_count` per combo; the sub-row counter (e.g. "35/36 runs") reads these from the optimization record's `completed_runs`/`estimated_runs`.

**Tab-specific active dots** — each Backtests tab has its own pulsing dot logic (not "any job running"): `runsActive = allRuns?.some(r => !r.sweep_id && r.status === 'running')` (includes opt-combo full backtests while running). `sweepsActive = allSweeps?.some(s => s.status === 'running')`. `optsActive = allOpts?.some(o => o.status === 'running')` — only fires when an actual optimization grid is running, NOT during a single-combo full backtest (`retry_single_optimization_run` uses `set_running=False` so the optimization stays `complete`). Running opt-combo full backtests appear in the Runs tab filter (`!r.optimization_id || r.status === 'running'`) with their OPT chip visible, then disappear once complete.

**Runs table columns** — "Score" = WorthinessBadge (Tier 1/2/3, the quality verdict; the `WorthinessLegend` "Score key" above the table explains the tiers). "Trades" = `run.trade_count` for at-a-glance volume. "Challenge" = firm name chip(s) showing which challenges the run was evaluated against. Score and Challenge are intentionally separated: score = how good, challenge = under what rules. Per-firm PASS/WARN/DISCARD detail lives only on BacktestDetail. There is **no Status column** — run status is a small `RunStatusIcon` glyph after the strategy name (running = pulsing accent dot, failed = red ✕, complete = green dot); a finished run is otherwise self-evident from its populated metrics. Nested rows (optimization/sweep/tune) keep their own status pill and still span `colSpan={12}` (column count is unchanged: Status removed, Trades added).

---

## ProgressCard pattern (SweepDetail / OptimizationDetail)

Both detail pages use an identical `ProgressCard` sub-component with:
- Left: status icon + label + segmented progress bar + counts
- Right: elapsed/duration timer (`useElapsed` hook) + Cancel button (while running) + Retry-N-failed button (when not running)
- Inline warning when failures accumulate during a run

**Terminal color scheme** (matches Smart Money terminal aesthetic):
- Complete (no failures): `border-accent/20 bg-accent/5` background, `text-accent` status label + icon, `bg-accent` progress bar, `text-accent` count
- Instrument/combo done pills: `border-accent/25 bg-accent/10 text-accent`
- Failed/partial: unchanged (red/amber)
- Running: unchanged (cyan spinner, already matched)

`useElapsed(startIso, endIso, running)` — counts up live when `running`, freezes at final duration when done.

Per-row retry in `FailedRunsTable`: a `RotateCcw` icon button calls `useRetryBacktest().mutate(run.run_id)`. Spinner activates on the specific row via `retryRun.variables === run.run_id`. `e.stopPropagation()` prevents the row-click navigation from firing.

---

## Strategy deployment manager

The "Deployed" sub-tab (`FilesTab`) has a drag/drop zone (`.cs`/`.mq5`), a file list sorted by platform then filename, trash-can delete, and overwrite/delete confirm modals. "Compile NT8" (`useTriggerCompile`) and "Compile MT5" (purple, only when MT5 files present; `useTriggerCompileMt5`) both open the generic `CompileModal` (props: `title` + `usePollHook`). The modal has a status-icon header (`StatusIcon`: spinner / green check / red X) + one-line summary, a body capped at `max-h-[85vh]` that scrolls, and a pinned footer. While running it shows staggered pulse **skeleton rows** (no second spinner) shaped like the result rows that replace them. On completion it renders the real `job.errors` / `job.warnings` **text** — not just counts — via `CompileSection` (color-coded, numbered, monospace lines: red `neg` for errors, amber `warn` for warnings); warnings show even on a successful compile. The elapsed counter ticks every second from a **local `setInterval`** (anchored to `started_at`, freezing at `completed_at` when done) — without it the count only advanced on each poll and visibly jumped. Strategy-file hooks live in `useLab.ts`: `useStrategyFiles`, `useStrategyFileSyncStatus`, `useUploadStrategyFile` (native `fetch()` + `FormData`, not `api.post`), `useDeleteStrategyFile`, `useTriggerCompile`, `useCompileStatus`, `useTriggerCompileMt5`, `useCompileStatusMt5`, `useDeployStrategy`. `useParamTypes(strategyId)` calls `GET /strategies/{id}/param-types` → `Record<string, 'int' | 'double'>` with `staleTime: Infinity`; used by `OptimizerModal` to validate int-param ranges; disabled when `strategyId` is null. Types: `StrategyFile` (+ `platform`), `StrategyFileSyncStatus`, `CompileJobStatus`, `DeployJobStatus`; `ScanResult` carries `orphans: string[]` (DB strategies whose source file is gone) + `warnings: string[]`; `ReconcileResult` carries `removed: string[]` + `warnings: string[]`.

**Scan vs Reconcile (bidirectional delete).** Scan is read-only: `useScanStrategies` (`POST /strategies/scan`) adds/updates and its success toast flags the orphan count (`N orphaned (source deleted — use Reconcile)`). Deleting a source file from the repo propagates to the DB row + the deployed VPS file ONLY through an explicit action: `useReconcileStrategies` (`POST /strategies/reconcile`). On the `Strategies.tsx` header, a red **Reconcile (N)** button appears next to Scan **only when the last scan found orphans** (`scan.data?.orphans`), fronted by the shared `ConfirmDeleteModal` (imported from `pages/Backtests`) listing exactly which strategies will be removed. On success it invalidates `['lab','strategies']` + the strategy-files / sync-status keys, and surfaces any per-strategy VPS-delete warnings as error toasts. The per-strategy Delete button uses the same backend `remove_strategy` path. See backend CLAUDE.md "Bidirectional delete (reconcile)".

Each row in `StrategiesTab` has a Deploy/Compile/Run action driven by the **content-aware** `StrategyFileSyncStatus` (`needs_deploy` / `needs_compile`, not the old presence-only `in_sync`). `StrategyRow` takes the full `sync` object (via `syncByStrategy[s.id]`), and the Status cell shows a version chip `v{current_version}` (title tooltip: "Local vN · running vM") next to the state pill: amber **Needs deploy** (local source differs from what's deployed) → amber **Needs compile** (deployed but not compiled from that content) → green **In sync**. The action button mirrors the pill: `needs_deploy` → Deploy, else `needs_compile` → Compile, else Run. `handleDeploy` tracks `deployingId` and on success invalidates `sync-status`. **First-run:** every strategy shows Needs deploy until deployed once through the tracked path (no deploy-hash recorded yet — see backend CLAUDE.md). `StrategyVersion` type + `GET /strategies/{id}/versions` expose the full version history if a per-strategy view wants it.

---

## What's built (status) — drained from `command-center/frontend/CLAUDE.md` (2026-08-13)

A status table answers *what exists and what state is it in*. This one had grown to
18.5 KB with 69% of its bytes carrying a date — the audit narrative for each page had
been written into the status column, so the answer to a one-word question arrived
wrapped in every finding ever made about that page.

**Every entry is reproduced here verbatim, nothing summarised away.** The index
in the CLAUDE.md keeps each entry's identity and lead sentence and links here for
the rest. ⚠ Where an entry explains something another file owns, the file next to
that code is the one that is right.

### Overview

**Status:** ✅ Live

Stat row + cards for each domain. **Audited 2026-08-05, 11 defects, every one of them rendering a healthy-looking answer** — a `No MT5 link` chip and a blind-bot stat branch, disabled jobs no longer wearing the "scheduled" pill, a fleet balance that names the bots that did not report, dated stale rows behind a dead VPS, a calendar window that survives midnight, a ticking server clock shared with the Calendar page, a sample floor under "best PF", and a running-backtest banner. See *The Overview was audited 2026-08-05*

### Bots

**Status:** ✅ Live

Monitor, control, configure, users. **Configure carries `DeployCard`** — the deployed version read off the VPS (hash / commit / date / params as deployed) plus the **Promote** button, which previews before it deploys and warns on the four states that make a version claim false. **Monitor's row shows a `No MT5 link` chip (2026-08-04)** beside the Running pill when the bot's process has lost its terminal — see *A blank cell is not a diagnosis* below. **Configure is a rail + detail panel (2026-08-04)** — a bot selector down the left, one bot's config on the right, a fleet version strip on top. It was one full section PER BOT with no selector. ⚠ **Only the selected bot's controls exist in the DOM** (1 promote button with 4 bots registered, measured), which is the misclick guard; the layout is downstream of that. **Monitor's `Fleet controls` card is danger-bordered, chipped `ALL N BOTS`, and every button carries its count** (`Stop all 4`) with the affected bots listed by name in the dialog; the row column header is `This bot`. 🔴 Its guards were computed off the demo/live-FILTERED list while the endpoints act on everything — fixed, and the card now says when the filter is hiding a bot. G11 closed

### Stress Tests

**Status:** ✅ Live

Grade card, source card, MC fan + drawdown + walk-forward + sensitivity charts. **Audited 2026-08-05 — the page had been driven end to end ONCE, three days before the engine underneath it was rewritten.** Drawdown now renders in the unit `dd_basis` names (and only that unit); `grade_reasons` / `phase_failures` / `results_error` are on screen; a null probability says `no limit to breach` instead of `0%`; the sensitivity radar is SIGNED off `pf_delta_pct` and drops unmeasured shifts rather than drawing them at zero; walk-forward shows out-of-sample trade counts and fades windows under the 20 floor; the fan no longer draws a drawdown limit it cannot support. Plus a Stop button, a windows-slider feasibility warning, and `phases_requested` driving the pipeline stepper. See *The Stress Tests page — audited 2026-08-05*

### News Calendar

**Status:** ✅ Live

`pages/Calendar.tsx` (`/calendar`) — Forex-Factory-style economic calendar off the free TradingView feed. Opens on today; day-summary strip, server-clock "now" line + countdown, actual/forecast/previous w/ beat-miss colour, currency chips (country flags), independent High/Medium/Low toggles, category dropdown. Whole week fetched, filtered client-side; all filter/week/day state in the URL. Shared helpers in `lib/calendar.ts`

### History-limited periods

**Status:** ✅ Live

`useHistoryLimit` + `PeriodPicker`'s `limit` prop. The date picker's minimum is the broker's MEASURED earliest backtestable date (probed server-side per broker, never hardcoded here), presets clamp to it, and a typed/pasted earlier date shows a one-click "Start at <date>" fix. Wired in `RunBacktestModal`, `BacktestDetail`'s `RerunModal` (which also disables Confirm below the floor) and `StackConfigModal`. Prevents submitting a window MT5 would answer with coarser bars mislabelled as the requested timeframe.

### Price-chart panel

**Status:** ✅ Live

Lazy klinecharts candlestick panel on BacktestDetail (`components/ChartPanel/`, own CLAUDE.md): TF switch (display resample up to **D1** + M1→H1 drill-down, the drill window ANCHORED ON THE VIEWPORT and paged like any other history + red "no earlier data" edge), sessions, generic overlays, indicators, day breaks, measurement + fib tools. The **fib LEVELS are configurable** TradingView-style — add, remove, retune, recolour or hide any level (extensions past 1.0 included) from a live editor, either as the tool's default ladder (gear on the tool strip, persisted) or for one drawing (its right-click menu); an un-customised fib follows the default live. **It SHIPS and opens on the timeframe the run TRADED, with no fetch** — the payload is capped by trimming the WINDOW (newest slice under `_CANDLE_CAP`; measured 33k candles / 3.1 MB / 17 months on a 2020→2026 15m run), never by coarsening the bars, so the chart paints on the first frame with no loading text and no swap. Older history **pages in as you scroll left** (one ~12k-bar chunk, ~1 MB, back to `spec.historyStartMs`) — and **says so while it does**: the blank strip you scroll into is shaded from the oldest loaded bar back with a `Loading earlier bars…` chip, so a page in flight no longer reads as the end of the data — so trimming costs reach, not access. **A page brings its own ANALYSIS with it (2026-08-02)** — structure overlays, fair value gaps, blocked and missed setups for that window (`?analysis=true`), merged into the panel's own — because all of those are emitted per-window and, until this landed, every layer you had switched on drew nothing past the shipped candles while its toggle still read ON. And and a **Go to date** pill beside the timeframe types you straight there instead, driving that same pager itself until the date is loaded (klinecharts only ever pages one chunk, and only on reaching the left edge), then centring the target bar. The Analysis menu opens with a **Deep debug** section — `Winners` / `Losers` / `Both` / `Off`, a radio sitting above the very rows it sets: one press gives Trades on with that outcome, **Fibs on**, External Structure + Fair Value Gaps on, Blocked and Missed off. That is the seven switches reading a run one trade at a time otherwise takes across two dropdowns, and it pairs with Step (press Winners, then ← / → walks only the winners, each arriving with the fib leg its entry was priced off already drawn). It presses the SAME switches the rows below it do — no second copy of layer state — and which preset is ticked is DERIVED from those rows, so changing anything by hand ticks `Off` instead; everything a preset does not name is left exactly as you had it. Beside it, **Step** (`◀ Loss 12/60 ▶`, or ← / → while the pointer is over the panel) walks the MARKERS instead of the calendar — previous / next, centred, with an accent dashed line on the one you landed on, paging history in through that same jump. **Its set is whatever the Analysis dropdown is showing**, oldest to newest: untick Winners and ◀ walks the losers, turn Trades off with Blocked on and it walks the refusals, leave both on and it interleaves them by time. It has no filters of its own on purpose — a second set would be a second place for the navigator and the chart to disagree. **Two header dropdowns split by question:** *Analysis* = what the strategy did with its signals — **Trades** (+ Winners / Losers filters, so a run reads as all-winners or all-losers), **blocked setups**, the trades that never happened (a setup the strategy had ready and its own rules refused: a dashed line pointing at the exact would-be entry price with a uniform `Blocked` tag parked clear of the candles, every refusing rule on hover, and one filter per reason), and **missed setups**, the ones that DIED partway (the same marker with the score on the tag — `2/3` / `3/3` — and hover showing what it had vs the one thing it didn't; the routine reasons start unticked, driven by `spec.missNoise`, so the layer opens on the misses worth studying). Both default OFF and are listed only when the run reports any. Directly before Fair value gaps sits **Fibs** — the fib LEG each trade was actually priced off, so a plotted trade says which retracement levels it went into instead of leaving you to redraw the fib by hand. Every level arrives as an explicit `(ratio, price)` pair the STRATEGY recorded when it PLACED the order, so **the browser does no fib maths at all** and the chart cannot land on a price the bot never used; the ladder spans the leg's start → the trade's exit, reaching back through the retracement rather than beginning at the fill, and each level is labelled on the RIGHT the way a hand-drawn fib is — **ratio only, no price** (2026-08-03, Aaron's call: the price is already on the axis and on the trade's own annotations). It draws the LADDER and nothing else; the `entry <ratio>` / `deepest <ratio>` accent chips it shipped with are gone, because the trade underneath was annotating the same two price rows and one number told twice by two layers is what made the chart read as doubled up. `entryRatio` / `deepestRatio` are still computed and still ride on the spec — they are the two readings a ladder cannot state — but nothing draws them today. `TRADE_FIB` is a SEPARATE overlay template from the fib TOOL on purpose — this one is data, not a drawing: locked, event-ignoring, and deliberately NOT following the fib editor's configurable ladder, because retuning your own tool must not restyle what the bot measured (only the factory COLOURS are shared). It reuses the trades effect's own predicates (loaded-candle clip, layer isolation, Winners/Losers), so the two layers can never disagree about WHICH trades are of interest — but it does NOT require Trades to be on, because a peer row whose layer draws nothing while its switch reads ON is the exact failure the per-window paging bug produced. Winners/Losers are therefore listed whenever EITHER row is on, so the fibs are never filtered by a control that is off screen. Default OFF and listed only when trades carry one — NT8/MT5 and pre-2026-08-02 Python runs show no switch, and there is no backfill because it would mean replaying the strategy, so an existing run needs a RERUN (Reload charts cannot supply it). Last in Analysis sits **Fair value gaps** — the gaps that were LIVE when something happened. The canonical `engines/fair_value_gaps/` engine is replayed server-side and a gap is drawn ONLY if it was open on the bar of a trade entry, a blocked setup or a missed setup (all of them when several overlap), so the layer answers "where were the gaps when this fired" instead of papering a 33k-bar chart with every gap the run ever saw. Default OFF with its box count. ⚠ The gaps are `mpc_assistant.pine`'s, deliberately NOT the stricter set the bot pins — a drawn gap is one the INDICATOR shows and not always one the entry rule counted. Below it, **Order blocks** (2026-08-03) — the supply/demand zones that were live on those same bars, off the canonical `engines/order_blocks/` engine, under the identical anchor rule (579 boxes on the measured run beside the gap layer's 661). Default OFF, and **not** in Deep debug. It needed no new template and no new effect — a plain `box` group and a second string in `ANALYSIS_GROUPS`. ⚠ **Its box is a fixed 30-bar STUB from the anchor candle, not a live-bar tracker** — so a block's box can end long before the block dies, or after the bar it died on; both are mpc's own drawing rule. ⚠ **No settings fork to warn about here** (the strategy files dropped order blocks entirely), which also means **a drawn block never explains an entry — the bot reads none.** *Structure* = what the market drew (structure groups + shipped indicators). Everything clock-driven — the session windows AND **Day breaks** — lives in the on-chart Sessions legend instead, so the two halves of "when did the day/session start" are in one place. Real spec via `useChartSpec`. **Market-structure overlays live** — the canonical `engines/market_structure/` engine replayed server-side (`chart_spec` → `structure_overlays.py`) into the 4 Structure toggles that mirror `structure_engine.pine` (External / Internal / Historic Internal Structure / Swing Point Labels — nesting like the Pine's via each overlay's `requires` list), default OFF, flat text tags anchored at each break line's midpoint (BOS/SOS/iBOS/iSOS), de-collided, on wick-anchored break lines

### News & Holiday filter

**Status:** ✅ Live (NT8 + Python)

**A pill on the Performance header that reshapes the page's REAL numbers** — no duplicated tiles, no section of its own (both were removed 2026-07-30). State lives in the page-level **`useNewsFilter`** hook because three things read it: the pill, the `PerformancePanel` (fed `news.filteredRun`, a synthesized `Run` built by `buildFilteredRun`) and the main Equity chart (`news.filteredCurve`). Popover lists BOTH exclusion rules as `ExcludeRule` checkboxes — bank holidays and high-impact news (with its before/after window sliders nested under it, default 15/30) — **both unticked by default (2026-08-01)**, so the page opens on the run exactly as traded; each row shows the trades it matches whether ticked or not. Every card's caption becomes its delta vs unfiltered (`KpiGrid`'s `compare` prop). **Refused rather than faked:** per-firm SIZED runs block the filter (sizing is path-dependent), the firm Evaluation card carries an `unfiltered` chip, `platform_sharpe` goes null, `sharpe_low_sample` is recomputed. Coverage-honest (untagged where no calendar data; the pre-`entry_ms` note offers "Reload charts" on NT8 only). **Forex/MT5 not wired — TODO #3** (needs MT5 `entry_ms`/`exit_ms` + non-UTC broker timezone handling)

### Portfolio stacks

**Status:** ✅ Live

Stacks tab on Backtests + `StackDetail` page. Layer 2+ Python strategies over one shared instrument/timeframe/costs/window. **StackDetail renders like a single backtest on the combined portfolio** — reuses BacktestDetail's exported `PerformancePanel` + chart components + `PriceChartView` against a client-side `composeCombined` payload (identical three-question panel, Equity/Price/Breakdown tabs, full price chart with structure/fib/measurement). New + Rerun share `components/StackConfigModal.tsx` (prefilled for rerun) — and so does the **Strategies page**: ticking 2+ python rows there reveals a gold **Stack N strategies** button that opens the SAME modal prefilled with them, so a stack is configured identically wherever you start it (the checkbox column only appears when 2+ python strategies are listed, and a non-python row has no checkbox because stacking replays python only). Per-strategy toggles drive everything (same `enabled` set, ≥1 always on); a leg's Back returns to the stack. **Smart reuse** — `CreateStackModal` calls `useStackPreview` (POST `/backtests/stacks/preview`) to show per-leg Reuse/Run chips; a leg whose exact settings already have a completed standalone run is reused (opens the real run on View), the rest re-run fresh. Costs default 0/0 (comm 0 / slip 0 / 15m) to match the Pine strategies (all pinned commission=0, slippage=0); these fields are cosmetic for Python runs (real cost comes from the account profile), so 0/0 keeps the display honest. Match is STRICT (any settings difference re-runs)


---

## The period filter — the full record (2026-08-16)

**Rules and the measured numbers: `../frontend/CLAUDE.md` → *The period filter*.** This is the part
that is story rather than rule.

**The ask.** Aaron: *"Is there a way to not rerun a specific period, and inside that period just
have, like, a filter on the backtest details page where I could just look at trades within a
specific period? And once I select that period, then everything on the page adjusts — the equity
curve, all the KPIs, the performance KPIs, the price chart, the breakdown, everything. The way I'm
thinking it will work is I could just click on the date range that's in the top box, and I could
filter. Maybe there's, like, a little filter button, and the minute I filter the whole page adjusts.
Right now I'm just having to rerun different periods."*

**The one decision that was not mine to make**, put to him before any code: with a window set, are
the dollars the ones the account really had at that date, or rebased? He picked rebased — *"it
should be like I only traded from 10,000 from that specific point in time"* — which is why the
window reads from the run's own opening deposit rather than from the $133,553 that was actually
there entering 2023 on `831ec44195ce`.

**The implementation was smaller than the design.** The page already had `buildFilteredRun` (a Run
synthesized from a trade list) driving the news filter and the costs pill, so the period filter is a
third caller. The rebase looked like it would need an R-replay and a compounding model; it collapsed
to one multiplication once it was noticed that a trade's dollar result is a fixed fraction of the
balance it was taken with, so the whole window scales by a single constant. That was checked rather
than argued: the replay `balance *= 1 + r × (risk_usd / balance_before)` from $10,000 over the 101
trades from 2023 lands at $11,911,354.78 and the scale lands at $11,911,347.71 — 0.000059% apart.

**What the build found that nobody had asked about.** Two sections of this page had never followed
ANY of its filters. The Breakdown tab (drawdown, daily P&L, long-vs-short) read `effRun`, and the
Performance-by-Regime table rendered the backend's whole-run rows — both sitting under a
Performance header that has said *"139 of 142 trades"* since the news filter shipped in July. That
is the same class as the audit findings this page keeps producing: nothing rendered an error, and
three charts confidently drew the wrong book under a heading that said so.

**The test that would not bite, twice, and it is the useful half of the day.** The Breakdown check
first compared SCREENSHOTS of the drawdown chart between a windowed and an unwindowed load, with
`Buffer.compare(...).not.toBe(0)`. It passed against a mutation that reverted the fix, because
Recharts animates on mount and two page loads differ by a few pixels of tween whatever the data is
— **a `not.toBe(0)` on a screenshot is satisfied by noise.** Rewritten onto rendered text, it used
`allInnerTexts()` on the SVG tick values, which returns `[null, null, …]` — and a row of nulls
compares equal to another row of nulls, so it passed a second time. Only `allTextContents()` scoped
to `.xAxis` gives real labels (`Jul '20`, `Jan 3 '23`), and only then does reverting the fix turn it
red for its own reason. **Two more entries for this folder's vacuous-pass list, and neither would
have been found by reading the diff — the mutation had to actually be run.**

**Left undone, deliberately.** The firm EVALUATION card is still graded server-side over every trade
and wears its unfiltered chip; a windowed grade would mean re-evaluating prop rules against a
rebased account, which is a backend question. Engine-sized runs refuse the filter outright.

---

## Fixtures pinned to a row — the three incidents (2026-08-16)

**The rule and the two answers: `../frontend/CLAUDE.md` → *A FIXTURE PINNED TO A DATABASE ROW*.**
This is the record of how it kept happening.

1. **`backtests.spec.ts`** — a check asserting a money figure ran into the millions, true only while
   one particular run sat at the top of the list.
2. **`tuning.spec.ts`, 2026-08-15** — eight checks died the day their baseline run was deleted, and
   every one of them pointed at the leaderboard, which was fine.
3. **`chart-paging.spec.ts`, 2026-08-16** — `const RUN = '211384ddbea4'` had left the lab. The run
   endpoint 404s, so the price chart renders "No price data", the `Go to date` pill never appears,
   and both checks die on a 120-second `locator.click` timeout whose stack points at the paging
   code. **Measured both ways**: the two lines this session added to `ChartPanel/index.tsx` were
   reverted and the failure was byte-identical, which is what established it as pre-existing rather
   than a regression from the period filter.

**The third one is what forced the split.** Repointing `chart-paging` at another literal would have
been the fourth instance waiting to happen — so it resolves now (longest-spanning intraday python
run carrying trades and a built spec) and derives its jump target from whatever it resolved. Six
other specs plus `param-gates` genuinely cannot resolve: they need a run carrying a VWAP series, a
recorded fib leg, candle-reversal marks, or a params set sitting entirely at defaults, and "any
completed run" supplies none of those. For those the pin stays and `requireRun` makes it speak.

**Two implementation notes worth keeping.**

`hasChartSpec` aborts after the response headers. The endpoint serves ~33 MB and the backend
ignores `Range` — measured: a `curl -r 0-100` still downloaded 32,983,708 bytes — so reading the
body just to learn a status code would pull it in full, per candidate.

**A syntax error in a spec is invisible to `tsc`.** The first draft of the `requireRun` wiring put
an apostrophe inside a single-quoted string in `candle-reversals.spec.ts`; `npx tsc --noEmit`
returned clean because the frontend's tsconfig does not include `tests/`, and prettier reported
nothing useful. `npx playwright test --list` parses all 20 files in seconds and is the check that
catches it — it is also where the suite's headline count should be taken from rather than
incremented by hand.

---

## The five things a browser spec drifts against (2026-08-16)

Fixing `chart-paging` earlier the same day left **16 failures across three specs nobody had
touched** — and every one of them was the page under test being RIGHT. They were reported as
"pre-existing, not from this change", which was true and was also where the reasoning had stopped.
Read together they are not three unrelated bits of rot. They are **one defect with five faces**,
and the row-shaped face — pinning a spec to a lab RUN, fixed earlier the same day and written up
above — is only the one that had a name. The other four are below.

The rule that came out of it, and the reason it is worth a section: **a test may depend on the
world, but it must not be able to fail SILENTLY-WRONGLY when the world moves.** Every one of these
failed loudly enough to be seen and quietly enough to be read as a regression — which is the
expensive half, because the next reader spends their afternoon in the feature.

### 2. Pinned to the WEEKDAY — `calendar.spec.ts`, 2 checks

`mockCalendar`'s default builder emitted one event per **weekday**, `[0,1,2,3,4]` from Monday. The
Calendar page **opens on today** (`Calendar.tsx`, the mount effect that patches `?day=` to today's
index). So on a Saturday or a Sunday the selected day held no events, the list rendered empty, and:

- *never shows the previous week under the new week header* timed out for 60s on
  `rows(page).first().textContent()` — there were no rows to read;
- *is absent on a week that does not contain now* found no `now-line`, because the line renders
  **inside the event list** and an empty day has no list to put it in.

Both were green five days in seven. 2026-08-16 was a Sunday.

🔴 **The file had already been bitten by this and had written it down** — the duplicate-events test
carries a comment that says, in as many words, that the page opens on today and a fixture built on
a fixed weekday renders empty on every other day. It then fixed **itself** with an explicit
`?day=1` and left the trap standing in the generator. Two later tests walked into it.

**A trap named in a comment is one the next test still hits.** The fix is `[0,1,2,3,4,5,6]` — the
weekend rows are the whole point — and the reason now lives on the `build` option, where anyone
adding a test reads it. The now-line check also gained the non-vacuity half it never had: an empty
next week has no now-line *either*, so it asserts rows **and** no line.

**Watched red by mutation.** `loadingWeek = isLoading` (placeholder week rendered again) reddens
the paging check at the `Loading …` banner; dropping the `isCurrentWeek ?` guard on `nowIdx`
reddens the now-line check with `unexpected value "1"`. Suite: 15 passed, and 1.6m → 36.8s, because
two 60s timeouts went away.

### 3. Pinned to the CALENDAR — `overview.spec.ts`, 1 check

```ts
await page.goto('/calendar?week=12') // US fall-back, 2026-11-01
```

`?week=` is an offset **from this week**, so that literal is a fixed calendar date written in a unit
that moves: it names a different week every Monday. It was true when written (2026-08-05: week 12
began Oct 26 and held Nov 1). By 2026-08-16 week 12 began **Nov 2**, the changeover had fallen into
week 11, and the check reported `Expected: 169, Received: 168` against a `localWeekEnd` doing
exactly the right thing.

**This is the same class as a run id and it does not look like one** — nothing about it reads as a
fixture. `nextDstWeek()` now scans `getTimezoneOffset()` forward a day at a time for the real
transition, converts it to a week offset, and expects **169h on a fall-back and 167h on a
spring-forward** (the offset RISES into standard time: EDT 240 → EST 300). No table, no country
assumption, no year.

⚠ It **throws** on a timezone with no DST, naming the resolved zone. A silent skip and a pass are
the same outcome, and this check would then go unwatched with the suite green.
⚠ It works because Node and the browser share the system timezone — `playwright.config.ts` sets no
`timezoneId`. Pin one there and the helper has to be evaluated in the page.

**Watched red:** `localWeekEnd` reduced to `fromMs + 7 * 86_400_000` gives 168 again.

### 4. Pinned to the REGISTRY'S SIZE — `overview.spec.ts`, 2 checks

```
Expected pattern: /1 of 1 not reporting/    Received: "Balance›—2 of 2 not reporting"
Expected pattern: /1 of 2 not reporting/    Received: "Balance›$9,996.992 of 3 not reporting"
```

Both mutated the real snapshot (`s.bots[0].balance = null`, or pushed a second bot) and then
asserted a denominator that is `bots.length`. Registering a second bot broke them.

🔴 **This file's own first test warns about exactly this, about a different noun.** Its comment
reads: *"a rendering rule must not be coupled to which jobs the fleet happens to contain, or
deleting a job silently deletes the guard with it."* That was written about `scheduled_jobs` in
August and never generalised to `bots` three tests below it.

The fix keeps the folder's discipline — **still built from a real bot object, so it cannot drift
from the model** — and **sets** the fleet rather than adding to it: trim to the bots the rule needs.
⚠ And the reporting bot **states** its balance instead of inheriting it: the live bot's balance is
`null` whenever its terminal is quiet, which would make that fleet 2-of-2 silent and the check green
for the wrong reason on precisely the days the Balance card matters.

**Watched red:** `reportedBal = bots` (a null balance summed as $0) gives `"Balance›$0.00demo
account"` — the original defect, verbatim.

### 5. Pinned to an EMPTY TABLE — `stress.spec.ts`, 11 checks

`stress_tests` held **zero rows**. Every check calls `anyStressTest()`, which threw
`no stress tests in the lab to mutate` before a page was ever rendered. **A whole feature's
regression suite had switched itself off** — on the page whose 2026-08-05 audit found 24 defects,
not one of which showed an error.

The dependency is **legitimate and was kept**: these eleven mock states the live box cannot produce
(a compounding run graded on percent, a walk-forward that crashed, a shift whose child backtest
failed), and they build every one by mutating a real `/stress-tests/{id}` response precisely so the
mock cannot drift into a shape the server never sends. Hand-writing a base fixture would have
traded a loud failure for a silent one.

So the answer was not to remove the dependency but to make it **one command to satisfy**:
`backend/scripts/seed_stress_fixture.py`. Monte Carlo only — no walk-forward, no sensitivity, so no
child backtests, no VPS, no platform lock; seconds rather than the ~70 minutes a full test costs. It
drives the **real** `run_stress_test_task` (a shortcut would be a hand-written fixture wearing a
database row's clothes), refuses when the lab already holds one, and **stubs the Telegram sender** —
completion notifies `notify.HEALTH`, and an ops channel that pings for test scaffolding is one
people mute. `grade` comes back `None` with no ruleset, which is correct: every grade is a statement
about drawdown against a limit and an unconstrained ruleset states none.

**Proven from an empty table**, not from the seeded state it was written in: the row was deleted and
the committed script re-ran it from scratch (322-trade run, `status=complete`), then 11 passed.
The suite's own failure message now prints that command.

### What this cost, and what it is worth watching

The three specs had been red for an unknown number of days and nobody was reading them, because 16
red checks on a green feature train you to scroll past. **The count is the symptom to watch, not
the individual failure** — a suite that is normally 16-red has stopped being a suite.

## The fleet strip's badge that never re-read — the full record (2026-08-28)

Rules and the fix: `command-center/frontend/CLAUDE.md` → *The fleet strip re-reads itself*. This is
the measurement behind them.

**Reported off the screen**, after a promote of `mpc_sos_fade_demo` that had plainly worked: the
Configure tab's strip read `1 restart pending` and `1 not frozen` over a banner reading
*"MPC SOS Fade is up to date · Deployed v263 · Backtester v263 · Deployed and restarted"*.

**MEASURED the same day, against the live backend**, and the count was not wrong — it was OLD:

```
GET /bots/mpc_sos_fade_demo/version
  hash          46565639b94d090caa66a8f9fa6cf9af
  running_hash  46565639b94d          ← a 12-char prefix of it: the bot HAD come back
GET /bots/mpc_bleg_demo/version
  frozen false, hash ""               ← benched, never promoted: `not frozen` was true
```

So one badge was stale and the other was correct and unreadable. **`GET /{bot}/version` costs 4.5s
(timed twice, warm)** — one SSH round trip per bot — which is what rules out a baseline poll and
sets the 15s interval.

**Why the single invalidation could never work.** `usePromoteBot` invalidates on the mutation's
success, which is the moment the HTTP call returns. What happens AFTER that: `promote.py` writes
`stop.request`, the runner notices on its own 10s poll, exits through its clean path, the startup
task brings a new process up, and only then does that process stamp its `source_hash` into
`bot_state.json`. The refetch lands somewhere in the middle of that and reads the old hash.

**The fail-watch, and the detail worth keeping.** With `refetchInterval` removed from
`useBotVersions` alone, the check goes red having observed `2 restart pending` and then
`1 restart pending`, never 0. The `1` is not noise: `useBotVersion` (unmutated, still polling) and
`useBotVersions` share one cache entry per bot, so the SELECTED bot's entry refreshed and the other
bot's never did. That is the evidence the strip needs its own poll rather than inheriting the
card's.

**A fixture that measures from a moment the subject has not reached yet.** The polling check first
failed on its OPENING assertion — the chip already read `0`. The mock served a stale hash for 3s
measured from `page.route(...)` registration, and the page's boot (navigate → bot snapshot → version
queries) spends more than that before anything asks, so the very first answer came back settled. It
anchors on the first REQUEST now. The failure looked exactly like the feature working.

## The stack page's two progress readouts (2026-09-03)

Reported off the screen while a two-strategy shared stack replayed. Rules:
`../frontend/CLAUDE.md` → *A running stack has ONE progress readout*.

**What was on screen.** A banner reading `Running — 0 of 2 strategies complete · auto-refreshing`,
and directly beneath it a section headed `THE SHARED ACCOUNT` whose only content was a second
spinner reading `shared · bar 43,520 / 630,993 · 5%`. Both were live, both described the same
replay, and the two numbers cannot be reconciled from the screen: one counts strategies, the other
counts bars inside the leg currently replaying. Aaron: *"I don't know why I have two terminal
looking things showing the progress of the strategies… you could do that with any same terminal."*

Below those sat a third statement of the same fact — a bordered box, ten rem tall, centred text,
reading *"Waiting for the first strategy to finish…"* — occupying the slot the charts use on a
finished stack.

**Neither extra element was a bug.** Each was individually reasonable and each had its own test.
The shared-account panel's spinner exists because `available: false` means *still replaying* and a
multi-minute replay with no feedback reads as a page that failed; that reasoning is sound and is
still why the branch exists. The defect is that nothing asked what the page looks like with all
three rendering at once, which is the ordinary state of every running stack.

**What the merge kept.** The bar counter is the finer measurement, so it drives the bar; the leg
count became its caption. Both numbers are still on screen, now under one heading, with the phase
translated out of the backend's own vocabulary (`solo:mpc_bleg` → *Replaying MPC B-LEG on its own
account*).

**What it deliberately did not absorb.** `SharedAccountPanel` has four branches and only ONE is
progress. Failed, cancelled and abandoned each carry a sentence — *the shared replay failed*, *this
will not arrive on its own, rerun it* — and a percentage cannot say any of them. `sharedInBanner`
excludes them explicitly, and the check that pins it renders a failed replay under a running stack
and asserts the failure text is still on the panel.

**Proof.** `tests/stacks.spec.ts`, 29 → 31 checks, all 31 green. Non-vacuity by mutation, three run:

| mutation | what went red |
|---|---|
| drop `!sharedInBanner` from the section's render guard | the panel COUNT — two readouts on screen, the reported defect exactly |
| drop `phase !== 'failed'` from `sharedInBanner` | the failure sentence swallowed into a progress bar |
| print `p.message` raw instead of the words | the banner reads `solo:mpc_bleg` |

⚠ **The panel-count assertion had to wait on the progress block first.** `toHaveCount(0)` is
satisfied while the whole page is still loading, so asserting it straight after `goto` passes
against its own mutation — the fifth instance of that trap recorded in this app.
