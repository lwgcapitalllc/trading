# Notes — Backtest results page — KPIs, costs and the period filter

The Performance panel and its cards, the News & Holiday filter, switchable costs, the period filter, and the 2026-08-06 audit of the Backtests list and detail page. Moved VERBATIM out of `command-center/frontend/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

### The Performance panel is four questions, not twelve peers

**Rebuilt 2026-07-31, replacing the 6+6 `KpiGrid`. Read this before adding a metric.**

Twelve equal cards with a fixed pixel height was the wrong shape three ways at once, and every
complaint about the old panel traces to one of them: **cropping** (`KPI_ROW_H` 196/228 — a constant
height on variable content, so the taller cards clipped), **lopsided cards** (`KPI_COLS` =
`1.4fr repeat(5,1fr)`, widened to fit one long money value and visibly uneven ever after), and an
**empty evaluation box** (`unconstrained` states no rules by design, so `EvalCard` rendered 300×196px
of nothing). None of the three is fixable by resizing; they are all consequences of the layout.

The metrics answer four questions — what did it **Make**, what did it **Risk**, can I **Trust** it,
and what is the **Verdict** — so there is one card per question, each with one hero number and its
supporting rows. Consequences worth knowing before you change it:

- **The 6+6 expand toggle is gone**, and with it both fixed heights. Three wide cards hold every
  metric at once, so nothing hides behind a chevron and rows flow instead of clipping. `KPI_ROW_H`,
  `KPI_ROW_H_EXPANDED`, `KPI_COLS`, `MoreMetricsToggle` and `TradeCountStandout` no longer exist —
  in `StackDetail.tsx` either.
- **The evaluation card became `VerdictCard`** — a fourth card, rendered FIRST (2026-07-31, second pass — it was a
  full-width ribbon in between). The empty box cannot recur because a ruleset with nothing to say
  simply has no rows. See *The verdict is a card, not a bar* below for why the content had to change
  shape to move, and what still uses the `ribbon` slot.
- **The trade count is `VerdictCard`'s hero**, at the same 34px as the other three, with its cadence
  beneath it (`≈2/month`) — it is the sample size every other number rests on, and cadence is the
  unit the root `CLAUDE.md` Trading Philosophy states the design target in. It appears exactly once
  on the panel; printing it in *Trusted* as well made the second copy read as a different number.
- **`deriveKpis` is unchanged and still the single derivation**, so the news filter's `compare`
  mechanism works exactly as before. Add a metric there first, then to a card's row list.
- **The whole panel collapses to its heroes** (`collapsed`, persisted under
  `performance_panel_collapsed`, **default ON** — hence `getPerfCollapsed`, since `getBoolPref`
  defaults off). Expanded, the panel plus its header fills the fold on a laptop and pushes the
  equity curve entirely off screen, and the headline and the curve are read together. The three
  heroes and the drawdown meter survive the collapse, so the default still answers "how did this
  run do" without a click. `StackDetail` passes nothing and stays expanded.
- **Height is measured, not eyeballed.** At 1670×940 with the params panel collapsed the section
  (header + cards) is **180px collapsed / 305px expanded**, from 234 / 345 with the ribbon and
  318 / 496 on the first build of this panel. Things that carried it, each worth knowing before you
  add height back: the card's **question shares the title's line** (its own row charged ~16px per
  card, forever, for a sentence nobody re-reads); the meter's **limit-label padding is charged only
  when a limit exists** (15px of blank card on every ruleset stating none); the **verdict left its
  own row** (44px + a 10px gap, in both states); and rows are `py-[4px] leading-[1.3]` at 24px each.
  Re-measure rather than estimate — the biggest single saving on the ribbon build was a sentence
  that wrapped, which was invisible in the source and only showed up on a real render.
- **Measuring gotcha, cost an afternoon:** Playwright's option is `newContext({ viewport })`.
  `viewportSize` is Puppeteer's name, is silently ignored, and every reading lands at the default
  1280×720 while the script claims 1670. Card *widths* are the tell — if the four sum to ~990 on a
  1670 run, the viewport never applied. `page.setViewportSize()` IS correct on the page object.

#### The verdict is a card, not a bar

**2026-07-31, second pass.** The verdict went evaluation-box → full-width ribbon → a card in the row. The
bar bought a row it did not need: 44px plus its gap, charged in both states, on a panel whose whole
point was fitting on one screen with the equity curve.

**Moving it was only safe because the CONTENT changed shape with it, and that is the transferable
part.** As a bar the rules were inline pills laid out by wrap — fine at 1330px, five or six lines at
a quarter of that. The grid is `items-stretch`, so a tall fourth card drags the other three up with
it, and you would trade one 54px row for something worse. As **rows** each rule is 24px whatever it
says, and each rule's explanation moved from a `title` attribute nobody discovers to the same ⓘ every
other row uses. Before moving anything else into that grid, ask whether it lays out by wrap.

Rules that hold it together:

- **The card anatomy lives at module scope** — `panelCardCls`, `CardHead`, `CardHero`, `PanelRows`.
  They were closures inside `PerformancePanel`; a second private copy in `VerdictCard` is exactly
  how the fourth card would drift out of line with the three beside it. Change the anatomy in one
  place and all four move.
- **`VerdictCard` is FIRST**, leftmost (`0.8fr 1fr 1fr 1fr`). The grade and the sample size are what
  you check before reading the three numbers to their right, and it inherits the position the
  ribbon's own verdict chip held at the panel's top-left.
- **`VerdictCard` has no question line.** At ~285px there is no room for a title, a question and a
  verdict chip, so the chip takes the aside slot the other cards use for `no limit set`.
- **The ruleset name is a caption under the hero, not a row.** It is identity, not measurement, and
  the row's value column is `whitespace-nowrap` — `Unconstrained (No Limits)` there would push the
  card wide. As a caption it truncates with the full name on `title`.
- **`verdict` and `ribbon` are separate props.** Two callers still want a bar and neither is a
  regression: `StackDetail`'s strategy legend is genuinely horizontal (one entry per leg, with its
  colour), and an optimizer combo (`isOptCombo`) has no verdict at all — just a prompt to run a real
  backtest, which earns the width. Passing `verdict` is what switches the grid to four columns.
- **Breakpoints are set by the longest rule label, measured.** `Daily DD ≤ $5,000` renders 118px at
  12px, plus its ⓘ and tick. So: weighted `1fr 1fr 1fr 0.8fr` from **xl** (verdict card ~285px at
  1670, ~202px at 1280 — fits), four EQUAL columns at **lg** (weighted there lands near 148px and
  would truncate the label to nothing useful), two columns below that. Measured across widths:
  180/305 at 1670, 1440 and 1280; 207/362 at 1200; 223/378 at 1024.
- **The `verdict unfiltered` badge became a `Graded on → all 142` row.** Same fact — firm rules are
  evaluated server-side on every trade, so the grade never follows the news pill — stated as a
  number instead of a label to decode.

#### A row is a label, a ⓘ and a number — nothing else

**2026-07-31.** Every row's explanation lives on the label's `InfoTip`, never beside the value.
Suffixes carried both a definition and a judgement (`4 days · consecutive losing`,
`3.63 · strong — wins 2× losses`) and cost twice for it: they re-explain a term the reader learned
on first read, and they make the value column ragged, because a column of numbers is only as tidy as
its longest sentence. Rules if you add a row:

- `PanelRow.tip` is **required**. Write what the metric IS, then what THIS value means — the
  `*Label` helpers (`sharpeLabel`, `pfLabel`, `concentrationLabel`, `zScoreLabel`, `winRateLabel`)
  are still the single definition of the words and now end their tip rather than the row.
- `PanelRow.value` is a **`ReactNode`, but keep it short** — usually a formatted number, or a tick
  or cross on a pass/fail rule row. The column is `whitespace-nowrap`, so a long value pushes the
  card wide rather than wrapping. Do not use `FitMoney` here — it measures a flex cell that shrinks
  to its content, decides the number doesn't fit and abbreviates a value with room to spare (that is
  why Net read `+$846.3k` in a card wide enough for `+$846,257` twice over). `FitMoney` is for the
  fixed-width hero only.
- The **delta** is the one thing allowed beside a value, because it is what the news filter was
  opened to ask. Unmoved rows print nothing.
- **Units get converted, not printed raw.** `1365 min` is a number the reader has to divide before
  it means anything; `fmtHold` gives `22.8 h`.

#### Colour marks the exception, not the sign

The obvious rule — green for positive, red for negative — fails three ways, so the panel does not use
it. On a strategy that works nearly every row is positive, so a wall of green ranks nothing. **Worst
Day** and **Deepest in $** can only ever be negative, so red on them is decoration on a definition.
And **Sharpe 0.91 is positive AND weak** — green would call it good, and on this very run the news
filter moves it 0.91 → 2.98 by removing 3 of 142 trades. The rule instead:

- the three **hero numbers** carry colour (each is its card's verdict)
- every **delta** is coloured in both directions — a change is the signal the filter was opened to
  find, and its direction is the point
- a **row** stays neutral unless it is an exception: an unexpected sign (a negative Net inside
  *Made*), or a value past a threshold (concentration ≥60%, PF <1, a ≥6-day losing streak)

Where a number is soft its **tooltip** says so in words rather than the value lying with a colour.
`exceptionCls(cls)` maps a value-colour helper to "no colour" for ordinary values, so the `*Cls`
helpers stay the single definition of what counts as bad while only the crossings get painted.
Sharpe is the one that moved (2026-07-31): it now goes **amber below 1.0**, which is not a sign
colour but the same exception rule as every other row — green-for-positive would have called 0.91
good, amber-for-weak is the threshold that should stop you.

#### Metrics that were saying the wrong thing — fixed 2026-07-31

All of these were unit or basis errors, not display bugs, and each looked plausible enough to
survive a redesign. **Every one of them is the same mistake: `daily_pnl` holds only days that
CLOSED a trade, and three separate metrics treated that sparse series as if it were the calendar.**
Check for it before trusting the next one.

- **`worst_losing_streak` is counted in TRADES.** `backtest/output.py:_worst_losing_streak` walks
  the trade list, not the day list; the row said "4 days". On a strategy that trades twice a month
  that reads as a far worse run of luck than it was — the real worst run of consecutive losing
  *calendar* days on that run is 2.
- **Time underwater is weighted by the CALENDAR, not by row count.** Counting rows answered "what
  share of ACTIVE days" while the label said "of days". 67% by rows, 71% by the clock.
- **Profit concentration is measured in RETURNS.** See below — this one was printing a false amber.
- **Sharpe zero-fills flat weekdays, and there is now ONE frontend definition of it.** The backend
  has always zero-filled (`metrics.zero_filled_daily_values`, and its docstring warns about exactly
  this); the frontend had two private copies that did not, in `computeFallbacks` and in
  `StackDetail.composeCombined`. Scoring only the days that traded asks "how good were the 142 days
  it traded" and then annualizes by √252 as if it had traded 252 of them — on the shipped run
  that is **2.96 against a true 0.91**, over 142 active days in a 1,447-weekday span. It surfaced
  as a news-filter delta of **+2.07 from removing 3 of 142 trades**, which is the tell: the filtered
  side fell back to the frontend formula while the unfiltered side used the stored backend one, so
  the "delta" was two different formulas, not a change. `dailySharpe()` in `BacktestDetail.tsx` is
  now the single frontend definition and reproduces the stored value to 15 significant figures —
  that equality is the regression test; run it before touching either side. A stack read 13.06.
- **A streak has no daily fallback any more.** `FallbackMetrics` no longer carries `worstStreak`,
  because there is no honest way to answer a trades-labelled row from a day list — `deriveKpis`
  reads `run.worst_losing_streak` and nothing else. Both synthesizers (`buildFilteredRun`,
  `StackDetail.composeCombined`) set it with the exported `worstLosingStreakOf(pnls)`, off trades in
  entry order. Until this was fixed, the filtered panel printed consecutive losing DAYS in a row
  that said "N trades".

#### The *Made* hero is DOLLARS, and the starting balance is on screen (2026-08-01)

The hero was the MULTIPLE (`1439.7x on capital`) with the dollars demoted to a row. Aaron's call to
swap them, and the reason is the second half of his complaint rather than the first: **the starting
balance appeared nowhere on this page**, so the multiple was a number with no referent — 1439.7x of
*what*. Now:

- hero = **Net dollars**; caption directly beneath = **`from $10,000`**, taken off the equity curve
  itself (`equity[0].equity - equity[0].profit`) rather than the ruleset, because a python run
  opens on its own deposit and that is what the multiple actually divides by;
- first row = **`Return on capital 1439.7x`**, the old hero;
- the caption survives the collapse, because the multiple in the rows below is meaningless without
  it.

**Keep the compounding caveat on both tooltips.** At a fixed % risk per trade the dollar figure is
exponential in the edge, so it is the number LEAST comparable between runs — which is exactly why
it had been demoted in the first place, and the trade-off is deliberate: the dollars answer "what
was this worth" directly, and the tooltip says to rank on R or profit factor instead.

A **`Costs charged`** row landed with it, and it appears ONLY on a priced run. Charged costs were
invisible until this date — the run row carried the settings and nothing reported the resulting
figure — and `costs_usd` now rides on each equity point (`EquityPoint`, backend AND frontend: the
model drops any field it does not declare, the third time that trap has been hit here). Printing
`$0` on an unpriced run would read as "trading was free" rather than "nothing was priced", hence
the row is hidden rather than zeroed. Its tooltip carries the compounding warning because the raw
charge and its effect are wildly different sizes: on the shipped run **$50,582 of charged slippage
moves the final balance by $1,630,361** — 32x — purely because a dollar not earned early never
compounds.

#### Two rows the Performance panel needed, and one column on the Runs list (2026-08-01)

An audit of run `f866873aa862` found **no arithmetic wrong on this page**. What was wrong was what
three true numbers let a reader conclude. Same class as *Metrics that were saying the wrong thing*
above, except nothing here was miscomputed — each number simply needed a companion beside it, and
a label change could not have supplied one.

- **Win rate 67.3% → a `Won / scratched / lost` row.** A trade that closed a cent up counts as a
  full win. On that run 45 of the 111 "winners" made under a sixth of a typical loss, every one
  exiting at exactly the breakeven-stop buffer — the stop doing its job, which is real risk
  control and is not an edge. The honest split is **40% won / 27% scratched / 33% lost**.
  `computeScratchCount` measures a scratch against **the run's own median full loss**, so the bar
  self-scales across strategies and account sizes with nothing to tune (for a fixed-risk strategy
  that median IS 1R); median rather than mean so one outsized loss cannot move it. It returns
  `null` — never 0 — with no losing trade, because 0 would read as "no scratches" rather than
  "no scale to measure against". Amber past a quarter of the book: at that point the headline win
  rate is describing something other than winning.
- **Profit concentration → a `Top 5 trades` row beside it.** The existing row splits the span into
  QUARTERS, so it answers *did the edge show up in one period*. The reader hears *did it come from
  a handful of trades*, and the two can disagree completely — that run reads 34% by quarter
  (spread evenly across 6.6 years) while 5 of its 165 trades made **47%** of everything won.
  High is not automatically bad, and the tooltip says so: a runner-based strategy is meant to be
  fat-tailed, so it means the edge lives in the tail, not that the run is overfit.
- **Max DD on the Runs LIST was dollars only.** `BacktestDetail` has had the peak-relative
  percentage since 2026-07-30 (*Drawdown is peak-relative* above); the list did not, and the list
  is where runs get compared. $1.7M of drawdown listed beside $14M of profit reads as ~12% where
  the honest figure is **56%**. The percent now leads with the dollars beneath it — the percent is
  what is comparable across runs of different sizes, the dollars are what a prop-firm limit is
  written in. `BacktestSummary.max_drawdown_pct` is backend-stored (the list ships no equity
  curves); a negative value is the backfill's "measured, no answer" sentinel.

Both trade-shape metrics are computed **client-side and returned from `deriveKpis`**, exactly like
profit concentration and for the same two reasons: the stored column is whatever basis was current
when a run finished, and the news filter needs every number recomputed over a subset.
`services/metrics.py` applies identical rules, so a stored row agrees without the page depending
on it.

#### Profit concentration measures the edge, not the account

**`computeProfitConcentration` weights each trade by its RETURN on the equity it was taken with,
not by its dollars, whenever the run compounded.** In dollars the metric reports the compounding
rather than the clustering it exists to detect: on an account that grows 85x the final quarter must
hold nearly all the dollars however evenly the edge is spread. Measured on run `d2ab68f9e884` —
dollar quarters of $9k / $49k / $71k / $1,039k read **89%** and printed the panel's only warning
colour ("edge clustered — overfit risk"); the same trades as returns read **40%** ("spread across
the test"). The amber was describing the account.

The switch is `equityBase(equity) > 0` — whether the curve carries a real account balance. A
%-of-equity strategy compounds and must be normalized; an NT8-shaped cum-P&L-from-zero curve is a
unit-size run whose dollars already ARE comparable across periods, and dividing those by a
fictitious balance would introduce the opposite bias. `StackDetail` already used the same
`equity[0].equity - equity[0].profit` idiom to find a stack's opening balance.

The panel **computes this client-side instead of reading `run.profit_concentration_pct`**. The
stored column is whatever basis was current when a run FINISHED, so preferring it would show a mix
of old and new figures depending on a run's age. `services/metrics.profit_concentration_pct` applies
the identical rule and `init_db` re-stamps history, so a stored row agrees — but the page does not
depend on that having happened.

#### The drawdown meter, and the two things it may never invent

`DrawdownMeter` gives the *Risked* hero the reference it needs — 54.9% is neither good nor bad until
you say what you would accept. Both references are drawn **only when real**:

- the **gold limit tick** is the ruleset's own `personal_max_drawdown_from_peak_pct`. Prop rulesets
  cap a *trailing dollar floor*, which is a different rule from a peak-relative percentage — those
  get no tick, and their rules show as `VerdictCard` rows instead. Do not convert one into the other.
- the **hatched extension** is the stress test's worst-1% simulated drawdown, gated on
  `dd_basis === 'percent'` (the dollar basis isn't comparable on a compounding run, and tests before
  2026-07-30 have no percent columns). With no stress test the caption says *"the simulated tail is
  unknown, not zero"* — an unmeasured tail must never be drawn as an absent one.

The track snaps to one of `METER_CEILINGS` (25/50/75/100) rather than scaling to the run, so two runs
of the same strategy stay visually comparable.

The Equity chart is a TradingView-style panel. **Its x-axis is the CALENDAR by default** (`xMode`, persisted; a Date / Trade # switch sits with the series toggles). Calendar is canonical: regime bands only have a true width on it, drawdown DURATION is a time metric, and it's the axis the tuning workbench overlays runs on — so the same run traces the same path on both pages. Trade # spaces every trade evenly and exists for per-trade forensics (streaks, excursions). `x` is the plotted position in whichever unit, and the regime bands, the run-up/drawdown ribbon and the starting-balance anchor (`windowStart` = the run's start_date in date mode) are all expressed in that same unit, so switching moves the chart together. Regime bands are built from ONE `date → regime` map (the run's full-calendar `regime_timeline` — see backend — falling back to `daily_pnl` tags on pre-timeline runs) and then PROJECTED onto whichever axis is live: `regimeBandsFromTimeline` (date) or `regimeBandsByIndex` (trade #, each trade taking its date's regime). The first band stretches back to the anchor and the last forward to the final point, and they render with `ifOverflow="visible"` — Recharts DISCARDS an out-of-domain `ReferenceArea` by default, which is why an earlier stretch silently did nothing. **Stretch AFTER filtering out UNKNOWN**, or the stretch lands on a band that never renders and the chart opens with a bare gap. Shared axis maths (`getXMode`/`setXModePref`/`dateMs`/`niceStep`/`monthTicks`/`monthLabel`/`tradeTicks`/`balTick`/`balanceTicks`/`regimeBandsFromTimeline`/`regimeBandsByIndex`) lives in `lib/chartAxis.ts` — used by BOTH equity charts so they can't drift. The cumulative-PnL line is **colour-split at the starting balance** (green above, red below — `startEq = data[0].equity - data[0].profit`, offset mapped to the fill bbox so the flip lands on the break-even line), the curve is **anchored** by a synthetic starting-balance point so it leaves the `startEq` line, the Y axis carries ROUND ticks with `startEq` INSERTED as one extra (starting balance always labelled — see *The dollar axis* below), and a dot on every trade point (hover → Balance + Favorable/Adverse excursion). Two opt-in `SeriesToggle`s: **one bottom-bar toggle** — on runs that carry excursion it draws the combined **Trade excursions** bar (solid net-result core + translucent favorable/adverse halo, in true dollars anchored on `startEq`), otherwise a plain profit **Histogram** — and **Run-ups & drawdowns** (green/red ribbon along the bottom, green while equity makes new highs). Regime bands skip UNKNOWN (chart matches the legend). The XAxis is `scale="point"` so the bars never shift the line. Excursion needs `favorable`/`adverse` on `models.EquityPoint` (else FastAPI drops them) — and so does `entry_ms`, which the News filter tags on; that one was missing until 2026-07-28, so read this as a rule, not a one-off.

**The Equity chart's DATA can be filtered — `equityCurve = news.filteredCurve ?? run.equity_curve`.** When the News & Holiday accordion is removing trades, this is the only chart on the page that follows it; the KPI grid beside it follows the same switch (`newsOnKpis`), and every OTHER number and chart on the page still reports the raw backtest. Two rules if you touch it. (1) A filtered curve MUST be rebuilt on the run's real starting balance (`equity = startBal + running profit`), never restarted from 0 — the chart derives `startEq` from its first point and anchors the axis, the break-even line and the green/red split there, so a zero-based curve silently rebases the whole panel. (2) Anything indexed off the curve must read the SAME curve — `regimeBandsByIndex` does, or in Trade # mode every band after the first removed trade sits one trade to the right of what it describes. Details in `FRONTEND_BUILD_NOTES.md`.

### The dollar axis — round ticks, and a suffix that does not run out

**Both halves live in `lib/chartAxis.ts` and every dollar axis on the run page uses them** — equity,
daily balance vs risk floor, drawdown-in-dollars, daily P&L. They were four hand-written formatters
until 2026-08-25 and each had its own version of the same bug.

🔴 **The y-ticks used to STEP FROM the starting balance, which carried that balance into every other
label.** On a $10,000 account whose curve reached nine figures the step was $50M and the axis read
`$10k / $50010k / $100010k / $150010k`. Every one of those was arithmetically correct and every one
was unreadable — the trailing "10k" is the opening balance riding along, and a reader takes it for a
corrupt number and stops trusting the axis. ⚠ **The lesson is about the ANCHOR, not the arithmetic:
anchoring on break-even is worth a lot at 2x and is pure contamination at 15,000x**, because the
thing being anchored to has shrunk to noise against the step. The round ticks are now computed
independently and break-even is INSERTED as one extra tick, which keeps the property that motivated
the anchor without paying for it on every label. A round tick within 0.35 of a step of break-even is
dropped so the two can never collide.

🔴 **The formatter stopped at "k", and that is a WRONG number rather than an ugly one** —
$150,010,000 rendered as `$150010k`, which reads a thousand times smaller than it is. It steps
k → M → B now, and the sign leads the `$` the way money is written (`-$40M`, never `$-40000k`).
⚠ **An axis label is the only place most readers ever see the SCALE of a run**, so a suffix that
runs out is exactly the class of defect *Never Do* means by "ask what a reader will CONCLUDE from a
number, not just whether it is correct".

⚠ **The drawdown chart passes its ticks EXPLICITLY** (`balanceTicks(0, worst * 1.1, 0)`). Recharts
derives its own from the padded domain, and that domain is never round — it was labelling
`-$45.1M / -$30.1M / -$15.1M`. Zero is that axis's anchor the way the opening balance is the equity
chart's.

✅ **Proof: `tests/chart-axis.spec.ts`** — five pure-function checks, no browser and no backend, each
watched RED by mutating the function under it rather than by deleting the feature. ⚠ **They are
Playwright specs, so they are NOT in `scripts/run_all_tests.sh`** — the frontend has no unit runner
and adding one was out of scope. Run them with `npx playwright test tests/chart-axis.spec.ts` from
`command-center/frontend`; they need nothing running. ⚠ **Run playwright FROM that directory** — from
the repo root it resolves a different config and reports *"did not expect test() to be called here"*,
which reads like a broken test rather than a wrong working directory.

### Drawdown is peak-relative — never over a static balance

**Fixed 2026-07-30. Read this before touching `deriveKpis`, `computeCalmar` or anything that divides by `balance`.**

A percentage of capital only means something if the denominator is the capital the account actually
had *at that moment*. Both drawdown-derived cards divided by the ruleset's `account_size`, frozen at
the opening balance, and on a compounding run that is not the account — it is the account 5 years
ago. The shipped `sos_fade` run (142 trades, $10k → $856k) printed **Max DD 1096.7%** and a
**red Calmar 0.11**. The honest figures are **54.9%** and **2.25**. Two of the six core cards were
arguing the strategy was bad.

- **`maxDrawdownPctOf(series)`** is the fix: worst drop as a fraction of the running peak. It also
  returns that episode's dollars and peak, because **the deepest DOLLAR drawdown and the worst
  PERCENTAGE drawdown are different events on a compounding run** — here $109,665 off a $330,303
  peak (33.2%) versus 54.9% off $16,748 (only $9,198). The card's sub-line must describe the episode
  its own value names; the deepest dollar figure moved to the tooltip, labelled as the prop-firm
  view. Putting them side by side is how the next wrong number gets written.
- **Calmar divides by that same fraction.** CAGR compounds, so the drawdown must too, or the ratio is
  measuring two different accounts. Follow-on: Calmar now **does** move with the Account balance
  slider — the old "capital-independent by design, the balance cancels" claim was never true and is
  gone from the tooltip.
- **This is the same defect the stress-test engine fixed the same day**, in a second file — see
  `backend/CLAUDE.md` → *Drawdown basis*, where Monte Carlo switched to a percent basis for exactly
  this reason. When a number is a percentage of a growing account, check the denominator grows too.
- 54.9% is also the figure the repo already recorded for this strategy (root `CLAUDE.md`, Run 12).
  The panel was the only place disagreeing with it — worth remembering as the tell.

Full implementation detail (exact card set, fixed-height math, per-metric fallback rules, chart-specific quirks like the equity tooltip's segment-key filtering and the MT5 duration gap): `command-center/docs/FRONTEND_BUILD_NOTES.md`.

---

## The News & Holiday filter — it reshapes the REAL KPIs

**Reworked 2026-07-30. Read this before touching `useNewsFilter`, `NewsFilterPill` or `PerformancePanel`'s `compare` prop.**

The filter has now shed a duplicate copy of the run's numbers **twice** — first its own 200px equity
curve, then its own five KPI tiles — and both times the answer was the same: **reshape the page's
real readout, never ship a smaller second one beside it.** It has no section of its own. It is a pill
on the **Performance** header (a row that was otherwise empty, so the control costs zero vertical
space) and it drives the actual `PerformancePanel` plus the main Equity chart.

**1. A filtered run is a synthesized `Run`.** `buildFilteredRun` clones the run, overrides what the
trades determine (net P&L, win rate, PF, avg win/loss, drawdown, equity curve, daily P&L regrouped
with regime tags carried over by date) and then **NULLS every field derived from `daily_pnl`** so the
existing recompute path (`computeFallbacks`, `computeProfitConcentration`) redoes it off the filtered
series. The nulling is load-bearing — a left-behind `sharpe` is the raw run's, sitting in a grid
labelled filtered. This is the same transform `effRun` does for per-firm switching and
`StackDetail.composeCombined` does for a portfolio; three callers now want "synthesize a Run from a
trade list", so the next one should extract it rather than write a fourth.

**2. Four things cannot follow the filter, and none of them is faked.**
- **Per-firm SIZED runs block it outright** (`newsBlocked`). Sizing is path dependent — remove trade
  #7 and #8's position size changes, and every trade after it. That is a re-run, not arithmetic. The
  sized curve is also re-indexed 1..N over only that firm's taken trades, so the news tags (keyed on
  raw indices) would not even line up. The pill disables with that reason.
- **The firm Evaluation card** is computed server-side over every trade; it carries an `unfiltered`
  chip while Performance beside it is filtered.
- **`platform_sharpe`** is NT8/MT5's own whole-run number — no filtered version exists.
- **`sharpe_low_sample` is RECOMPUTED, not inherited.** Removing trades can only push a run *toward*
  too-few-days, so carrying `false` over would silence the warning exactly where it starts to matter.

**3. The Equity chart is gated on the SAME switch as the grid** (`newsOnKpis`). Holidays are excluded
without anyone touching a control, so on a blocked run the chart would otherwise quietly draw a
filtered curve under unfiltered numbers.

**4. Both exclusion rules are on screen, and both are switchable.** Bank holidays used to be
hardcoded always-on with no control and no row. That is what made the panel unreadable: the pill
counted trades being removed while the only visible switch said the news ones were *kept*, and
nothing accounted for the difference. Now each rule is an `ExcludeRule` row — tick, name, and **the
trades it matches whether or not it is ticked**, so the row doubles as the price tag on turning it
on. **BOTH rules default OFF (2026-08-01, Aaron's call)** — the page opens on the run exactly as
traded, so every figure on it is the backtest's own result and ticking a rule is a deliberate
what-if. This replaced two different defaults for one reason: a filtered default means the headline
number on screen is not the run's, and nothing about a checkbox further down the page makes that
obvious. Holidays had defaulted ON, and news followed the strategy's `avoid_news`, so the default
silently DIFFERED BETWEEN STRATEGIES — two runs over the same window could open on different trade
counts with no indication why. `strategy.avoid_news` is still real metadata; it just no longer
decides what you see first, and `useNewsFilter` no longer takes it. Because a trade can match BOTH rules, `excluded` is measured off the kept list, never summed
from the two counts.

**5. Every label is a COUNT, never a state word.** "News kept" / "news filtered" read as "nothing
removed" while holidays were going out regardless. The pill says `Excluding N trades` and each rule
row its own count. ⚠ **Said ONCE since 2026-09-13**: the header's `139 of 142 counted` and the
popover's footer total restated the pill and are gone; the header keeps only the PERIOD's
`N of M trades`, which nothing else shows. A refused pill reads `Not available`, reason on its title.

**6. Deltas replace each row's note, they don't crowd in beside it.** `PerformancePanel`'s `compare`
prop runs the extracted `deriveKpis` a second time against the unfiltered run; `rowSuffix` then swaps
the standing note (`· 3.63:1 R:R`) for the delta, and `heroDelta` does the same beside the big number.
The note is read once; the delta is the answer to the question the filter was opened to ask. Zero
extra height. **A row that did not move says nothing at all** (2026-07-31) — the old grid printed
"unchanged vs unfiltered" on every card, which was eight lines of text to communicate that nothing
happened. Deltas are the one place colour still tracks direction rather than exception, because a
change IS the signal here.

---

## Costs are switchable in TWO places, and the split is about arithmetic, not about UI

**Built 2026-08-02, extended to the run page 2026-08-03 at Aaron's request.**

The **Run backtest modal** (from `Strategies` or `StrategyDetail`) chooses the costs a run is
MEASURED at — one row per layer in `python_runner.COST_LAYERS`, every one **OFF by default**, gated
on `strategy.runner === 'python'`. **`BacktestDetail`'s Performance header now also carries a Costs
pill** (`CostFilterPill`, beside the News & Holiday one) that charges costs onto a run that already
happened, reshaping the real KPIs and the Equity chart without re-running anything.

⚠ **The first version of this section claimed a run-page toggle was impossible, and it was wrong.**
The argument was that a cost changes what the trades would have been, so a page-level control would
flip a number while the trade list under it stayed put. The premise is right and the conclusion does
not follow. **Every cost that CAN be re-priced costs a fixed amount of R regardless of position
size** — a spread over a stop distance, a commission over a stop distance — so the R is knowable
even though a charged run compounds into different position sizes, and the dollars follow from
re-walking the balance. Proven against real replays in `backtest/tests/test_reprice.py`; on the live
161-trade run `75ccc776d10c` the pill reproduces a real charged replay to **37¢ on $16.3M**. Left as
a standing reminder that "this cannot be derived" deserves the same evidence as any other claim.

**Where the split really falls** is on whether a cost changes WHICH trades exist:

| | re-priceable on the page | needs a re-run |
|---|---|---|
| | spread, commission, swap | `bid_ask_fills`, `slippage` |
| why | a fixed R per trade, size-independent | changes which setups fill / which exits were market orders |

`bid_ask_fills` moved the reference run 161 → 159 trades with four setups that never existed on the
free path — no arithmetic over a stored trade list can invent those. The server names such layers in
`needs_rerun` and the pill SAYS so; it never silently drops one and shows the rest under the same
label.

Rules the pill has to keep:

- **Costs compose BEFORE the news filter, never after** — `useCostFilter(run)` then
  `useNewsFilter(costs.repricedRun ?? run)`. A cost is a property of a trade, so it has to be
  charged before anything decides which trades count. With nothing charged the news filter gets the
  run's own object, reference-identical.
- **It rebuilds through `buildFilteredRun`, the same function the news filter uses.** One definition
  of "a Run derived from a trade list" is what stops the two controls drifting into different
  answers for the same KPI.
- **Refused under a firm's sizing, on the same guard as the news filter** (`newsBlocked`). A sized
  curve is PATH DEPENDENT — charging trade #7 changes the balance going into #8 and therefore its
  size — so there the cost is not size-independent and the whole justification evaporates.
- **`is_exact` false must reach the reader.** Two different causes, both captioned: a `swap` layer
  (accurate to ~0.3%, because its real charge depends on which bars existed and holiday closures
  are not in the stored trades) and `derived_basis` (a run predating the stored per-trade `r` /
  `risk_usd`, accurate to ~0.02%). Neither is "indicative" — but rendering either identically to an
  exact figure is how a number nobody measured comes to be trusted.
- **A trade the server did not price back voids the whole view** rather than passing through at its
  old value, which would show a partly-charged book as a fully-charged one.
- **Each row states its own price, and in R.** `CostRule` exists because the first build reused
  `ExcludeRule` — right for an exclusion rule, which counts the trades a release landed on, and
  meaningless for a cost, which touches every trade — so every row rendered a hardcoded
  `0 trades` that looked exactly like real data. **The unit is load-bearing:** a layer's DOLLAR
  cost depends on which others are on (charging one changes the balance, so every later position
  is a different size), so three dollar figures would not sum to the total beneath them and the
  panel would read as broken while every number in it was right. In R the size cancels and the
  rows add up exactly — pinned in `test_reprice.py` and `test_run_repricing.py`.
- 🔴 **THE PILL AND THE FOOTER CARRY THREE NUMBERS, AND NAMING ONLY TWO OF THEM READ AS A LYING
  PAGE (fixed 2026-08-03, reported by Aaron from the screen).** The footer said
  `−12.08R charged · $332,371 after compounding` and the pill headline said
  `Charging $332,371` — while the Net hero six inches away fell by **$18,200,741**. Both figures
  were correct and they are not the same quantity, so the only way to reconcile them was a
  subtraction the page never showed, and the honest conclusion from the screen was that the
  costs feature was broken. Worse, `total_cost_usd` is the FEES and "after compounding" is the one
  caption that does not describe them. The three, on run `75ccc776d10c`:

  | | | |
  |---|---|---|
  | **Charged** | `total_cost_r` | −12.08R — the size of it, and the only additive unit |
  | **Fees charged** | `total_cost_usd` | $332,371 — what actually left the account |
  | **balance impact** | `netBefore − netAfter` | $18,200,741 — 55x the fees |

  The gap is compounding and nothing else: at ~10% risk over 161 trades a fee paid early also
  costs everything it would have grown into. **The pill headline is now R** (`Charging 12.08R`) —
  a pill has room for one number and R is the one that cannot contradict the page, is what the
  rows above it sum to, and is comparable between runs. Both dollar figures live in the popover
  under their own names via the `Figure` row, with the ratio spelled out. **`useCostFilter` returns
  `netBefore` / `netAfter` / `balanceImpact`, summed off the SAME rows the Net hero sums**, so the
  pill and the card cannot disagree about what moved. The `Costs charged` KPI row was renamed
  **`Fees charged`** for the same reason — the old name invited exactly the subtraction that makes
  the two look like a contradiction.
- 🔴 **`cost_usd` IS SIGNED, and `-Math.abs()` on it was a live 25% overstatement (fixed
  2026-08-03).** A short's gold swap is a real CREDIT (+26.98 points/night on Vantage) and can
  exceed the spread on the same trade, so `cost_usd` goes negative — on the reference run **39 of
  161 trades are a net credit**. Forcing the sign booked every one of them as a charge, so the
  `Fees charged` row read **$415,990 against the pill's true $332,371**, and **$514,315 against
  $252,998 on swap alone — 103% high**. Two numbers, one label, six inches apart. The stored
  convention is negative = charge and `cost_usd` is the other way round, so the view SUBTRACTS it;
  it also adds to the point's own `costs_usd` rather than replacing it, so a run priced at replay
  time keeps its own charges in the row that names them.
- 🔴 **The pill was live under a firm's SIZED numbers while the page ignored it (fixed
  2026-08-03).** `costOnKpis` has always required `!newsBlocked`, so the charge correctly never
  reached a sized curve — but `CostFilterPill` took no `blocked` prop, so it stayed interactive,
  fetched, and read `Charging 12.08R` over numbers that had not moved. It takes the same
  `blocked` the news pill does now (`Not available`, disabled, reason on the title). A sized curve
  is PATH DEPENDENT — charging trade #7 changes #8's position size — so the size-independence the
  whole control rests on is genuinely absent there.
- 🔴 **A server REFUSAL rendered as "Charging nothing" (fixed 2026-08-03).** `useRunReprice`'s
  `isError` was never destructured, so a 400 left `report` undefined → `view` null → `active`
  false → the label read *Charging nothing* with the reader's boxes still ticked. `reprice.py`
  refuses rather than guesses on purpose (a curve missing an entry price, a stop or a size is a
  re-run, not arithmetic) and that discipline is worth nothing if the UI shows the refusal as
  "no costs apply". The pill now says **Can't price this run** and prints the server's own
  message, which always names the missing thing.
- **The BROKER is named in the popover header** (`· vantage demo`). The two profiles differ by 50%
  on the gold spread ($0.22 vs $0.33), so a charge with no broker beside it is a figure whose
  provenance the reader cannot check.
- **A layer this broker does not charge says so in words** — `none on this account` rather than
  `0.00R`, which reads as a failure to compute. A demo pays no commission and that is a finding.
- **A layer the RUN charged renders ticked and LOCKED** (`charged in the run`, readout `in the
  run`). It is already in every number on the page; the server refuses to charge it again (see
  `backend/CLAUDE.md` → *already_charged*), and it cannot be charged OFF from here either, because
  the stored trades were measured with it. The row states no R on purpose — what that charge came
  to is baked into the trades and never reported separately, so any figure there would be invented.
- **The report is fetched with NOTHING ticked too**, because that is when the per-layer prices are
  most useful: you see what a layer would cost before turning it on, exactly as the news filter
  shows each rule's trade count whether or not it is applied.

**⚠ The trade count does NOT move, and that is correct — expect it to be reported as a bug.** It
already has been, from the screen. Spread, commission and swap change what each trade was WORTH;
only `bid_ask_fills` changes which trades exist, and that one is refused here. Verified end to end
on run `432aff31f374` (73 trades, Aug 2023 → Aug 2026), where everything else moves:

| | as traded | costs on |
|---|---|---|
| trades | 73 | **73 — unchanged, by construction** |
| net | $573,812 | $485,984 |
| win rate | 65.8% | 60.3% |
| profit factor | 4.04 | 3.83 |
| avg win / avg loss | $15,881 / −$7,539 | $14,945 / −$5,918 |
| worst drawdown | 57.2% | 60.1% |

Two things in that table are worth keeping. **The win rate falls 5.5 points because four trades
flip from winner to loser** — +$12, +$68, +$207 and +$376 becoming −$26, −$133, −$1,315 and
−$2,331 — i.e. scratches that only looked like wins because the run was frictionless. And
**drawdown gets WORSE while profit falls**: a cost does not merely shave the top off, it deepens
every losing stretch, so the two headline cards move in opposite directions and neither is wrong.

⚠ The RISKED card's percentage will not match a hand-calculation from the starting balance —
`ddWorst` rebases the curve onto the account-balance slider (`rebaseEquity(equity, balance)`), so
its denominator differs by design. It is still derived from the RE-PRICED curve, which is what
makes it move at all.

Four things about the Run modal that would each silently mislead if changed:

- **The spread is never typed.** `useBrokerProfiles` (`staleTime: Infinity`) fetches
  `GET /backtests/broker-profiles` and every detail string on those rows — the `$0.22` spread, the
  swap per night — is rendered FROM that response. A number hardcoded into a form is a second claim
  about what the backend charges, and that exact defect (the Run modal's old futures 2.25/1 reaching
  a forex run) is why this whole area was rebuilt.
- **Spread and "model bid/ask fills" are mutually exclusive**, enforced in `toggleLayer` by unticking
  the other. They are two ways of pricing one spread; both on bills it twice.
- **`cost_layers: []` and `cost_layers: null` must render DIFFERENTLY.** The detail row is gated on
  `run.cost_layers != null`: `[]` means the run was asked to charge nothing, `null` means the run
  predates the switches. Showing "no costs" for both would claim a deliberate free run where there
  was only an older contract.
- **Two rows are tagged, and the tags are the point.** Slippage says it is a guess (it is the one
  cost history cannot measure), and bid/ask fills says it moves trades (it is the only layer that
  changes which setups fill). A reader ticking either should know that before the run, not after.

---

## The period filter — read a WINDOW of a finished run, with no rerun (2026-08-16)

**`useDateFilter` + `PeriodFilterChip` in `BacktestDetail.tsx`.** Aaron: *"Is there a way to not
rerun a specific period… just have a filter where I could look at trades within a specific period?
And once I select that period, everything on the page adjusts — the equity curve, all the KPIs, the
price chart, the breakdown, everything. Right now I'm just having to rerun different periods."*

The third control that reshapes this page's REAL numbers instead of shipping a second set beside
them, and it rebuilds through the same `buildFilteredRun` the other two do. **The period chip in
the page header IS the control** — it already stated the run's window, so making it clickable was
cheaper than a fourth pill, and there is deliberately no second copy on the Performance header.

🔴 **THE REBASE IS EXACT ARITHMETIC, NOT A MODEL, AND EVERYTHING RESTS ON IT BEING LINEAR.** He
asked for a window to read *"like I only traded from 10,000 from that specific point in time"*. The
tempting implementation replays each trade's R onto a fresh account and compounds it. That is
unnecessary: a trade's dollar result is a fixed fraction of the balance it was taken with, so
**scaling every profit in the window by ONE constant — the run's opening balance over the balance
entering the window — reproduces that replay to the cent.** ✅ MEASURED on run `831ec44195ce`,
2023-01-01 → end: the scale is ×0.074876 and lands at **$11,911,347.71 against the R-replay's
$11,911,354.78 — 0.000059% apart**, i.e. floating point.

⚠ **EVERY RATIO IS THEREFORE UNCHANGED BY THE REBASE** — profit factor, win rate, R, Sharpe,
peak-relative drawdown, concentration. ✅ Verified identical to 9 decimal places on that run
(PF 3.010326545, win rate 0.673267327, max DD 45.259156%). **If a ratio ever differs, the scale has
stopped being a single constant and the rebase is broken — do not "fix" it by special-casing the
ratio.**

⚠ **IT IS NOT A RERUN AND THE PICKER SAYS SO.** A rerun of 2023→2026 warms its engines from 2023
and sizes from $10,000 the whole way; the window carries the full warm-up from 2020 and each
trade's ACTUAL risk fraction, which drifted 5.9% → 66.4% on that run (risk is measured to the
trade's current stop). They agree on shape and on R and will not agree trade-for-trade.

⚠ **The picker states the rebase where the window is CHOSEN**, naming the balance it reads from,
the balance the account really held, the scale, and that ratios are untouched. A silent rebase
would put a balance nobody ever had under a headline that looks like the run's.

### Composition, and the one correct order

`costs → period → news`, in `BacktestDetail`. A **cost** is a property of a trade, so it is charged
before anything decides which trades count. The **period** then cuts and rebases, because the scale
is read off the balance entering the window and that balance moves once costs are charged. **News**
is last: it removes trades from whatever book the two above settled on, and its own rebuild anchors
on the first trade it is handed, which is already the rebased one. With nothing on, each `??` hands
the next filter the run's own object, reference-identical.

- ⚠ **The window lives in `?from=`/`?to=`** and both writes MERGE the existing params — house rule,
  and `setSearchParams({from})` alone drops `?tab=` (already recorded on the Bots page).
- ⚠ **`active` requires all three of** a window being set, it actually narrowing, and the rebase
  being possible. A window covering everything must leave the page reference-identical, and a
  window entering on a zero-or-negative balance is REFUSED rather than scaled by a made-up number.
- ⚠ **An empty window says the strategy stood still.** A real answer, and the one most easily
  mistaken for the filter being off.
- ⚠ **The compare baseline follows the period.** With a window set, the news and cost deltas ask
  what they did INSIDE it; comparing a windowed book against the whole run would put a delta on
  every row that is really the window wearing a checkbox's name. **The period itself shows NO
  delta** — it is a different span, not a what-if over the same trades.
- ⚠ **Refused under a firm's sizing, on the same guard as the other two, for a DIFFERENT reason.**
  Slicing a sized curve by date is honest arithmetic; the problem is that a firm's account opened
  at ITS `account_size`, so rebasing onto the run's deposit would state a prop account that never
  existed.
- ⚠ **The drawdown chart's firm LIMIT LINE is withdrawn while a window is rebased**, and only then.
  The limit is a dollar figure written against a real account; the windowed curve is scaled onto a
  different one. News and costs do not rebase, so they keep it.

### Two things it fixed that were NOT part of the ask

🔴 **The Breakdown tab read `effRun`, so it followed neither the news filter nor the costs pill** —
three charts under a header reading *"139 of 142 trades"* drawing all 142, since the day each pill
shipped. It reads `kpiRun` now, which IS `effRun` whenever no filter applies, so sizing is
unaffected.

🔴 **`Performance by Regime` rendered the run's server-computed rows under an already-filtered
panel.** `computeRegimeBreakdown` is a faithful port of `services/metrics.compute_regime_breakdown`
— the second frontend evaluator this repo has accepted, on `dailySharpe`'s argument. ⚠ **THE
EQUALITY IS THE REGRESSION TEST:** handed a run's own full trade list it must reproduce
`run.regime_breakdown` exactly (✅ byte-identical on `831ec44195ce`). Change one side and re-run it.
⚠ Keep the MT5 two-rows-per-trade rescale; dropping it makes the table disagree with the backend on
every MT5 run.

### The price chart follows by being handed LESS DATA

`clipSpec` filters the five timestamped arrays and raises `historyStartMs`. **ChartPanel is
untouched** — a `range` prop threaded through 4,300 lines would be a second place for "what is on
screen" to be decided, on the chart that already owns its viewport. ⚠ A SPAN overlay (box/hline) is
kept when it OVERLAPS the window: an order block opened earlier and still live is what the trades in
view are reacting to. ⚠ `missNoise` is NOT clipped — reason LABELS, not records. ⚠ Times parse as
UTC, matching the emitter, or the edge shifts by the reader's offset. ⚠ Memoised at the call site:
156k candles and 29k overlays on a 6-year M15 run.

### Proof

- **`scripts/check_period_rebase.mjs`** — the arithmetic, outside the browser, because these are
  numeric IDENTITIES and asserting them through `FitMoney`'s formatted text would be asserting on
  the formatter. 5 checks + a guard that the dollars really moved. ✅ Green, ✅ proven by mutation
  (`scale = 1` reddens the R identity, the drawdown invariance and the guard). ⚠ It reads the
  STORED `equity_curve.json` for the R identity — `risk_usd` is on disk and NOT declared on the
  backend's `EquityPoint`, so FastAPI drops it. This repo's "the model drops what it does not
  declare" trap, met as a limit on what can be PROVEN rather than as a rendering bug; nothing in
  the browser needs the field.
- **`tests/period-filter.spec.ts`** — 9 checks, 8 green, 1 skipped (needs an engine-sized run). ⚠
  **A fail-watch against HEAD is vacuous for most of it** (the control did not exist, so a red
  proves the locator and nothing else) — **non-vacuity is by MUTATION, named per check**. The
  Breakdown and regime checks are the two watched red against HEAD for the right reason.
- 🔴 **`lib/inputs.ts` → `DATE_INDICATOR_CLS`, and EVERY `<input type="date">` must carry it.**
  Chrome draws `::-webkit-calendar-picker-indicator` as a near-black SVG, so on this theme the
  calendar button is an invisible glyph on an invisible field — reported off the screen the day this
  shipped (*"can't see the calendar icon"*). ⚠ **The fix already existed and had not travelled:**
  `PeriodPicker` solved it privately when it was written, and the two date inputs added since
  (`ChartPanel`'s Go-to-date, this popover's two) never inherited it. It is a shared constant now,
  in `lib/` rather than in `PeriodPicker` — `ChartPanel` is strategy-agnostic and must not import
  page furniture. ⚠ `invert`, never a colour, so it survives a theme swap. ⚠ The browser check
  strips the class at runtime and requires the input to LOOK different; **it deliberately does not
  assert the class NAME**, which is a spelling rather than the property.
- 🔴 **TWO NEW SHAPES OF VACUOUS PASS, both found in one check** (full story:
  `../docs/FRONTEND_BUILD_NOTES.md` → *The period filter*). **Never assert a Recharts change by
  SCREENSHOT** — it animates on mount, so two loads differ by tween whatever the data is and
  `not.toBe(0)` passes on noise. **Never read SVG tick text with `allInnerTexts()`** — it returns a
  row of `null`, and nulls compare equal to nulls, so that passes too. Use `allTextContents()`
  scoped to `.xAxis`, and assert a VALUE (`Jul '20` → `Jan 3 '23`), not merely that two rows differ.

### The same window on a STACK, and the module both pages now share (2026-09-03)

Aaron: *"one thing that is missing is the date filter feature I have on standalone backtest doesn't
exist on stacked backtest."* It does now, and the interesting part is what had to move.

🔴 **THE ARITHMETIC LEFT THIS PAGE RATHER THAN BEING COPIED TO THE OTHER ONE.** The filter, the
bounds and the rebase constant live in `src/components/periodWindow.ts` (pure) wrapped by
`src/hooks/usePeriodWindow.ts` (URL state); `useDateFilter` here is now a thin run-shaped wrapper
that adds `buildFilteredRun`, and `StackDetail` wraps the same hook its own way. **`PeriodFilterChip`
is exported and typed to the window's own shape, not to this page's filter** — typing it to
`DateFilter` is precisely what would have forced a second chip. Both pages multiply every dollar
they show by that one constant, and two implementations of it means two pages that can disagree
about what a window is worth while both look right — the shape the rule/evaluator pair already
drifted into across the python/javascript boundary here.

⚠ **On a stack the window is handed to `composeCombined`, never applied to its result.** That
function derives EVERYTHING — per-leg counts and R, the KPIs, the drawdown, the daily series, the
overlay lines — so filtering the books at the source is what keeps them in step. Filtering the
composed object instead leaves each of those a separate place to remember, which is how a filtered
headline ends up over unfiltered rows. ⚠ **The opening balance is read off the UNWINDOWED books
on purpose**: under a window a leg's first point is the first trade IN it, so taking the deposit
from there would redefine the account as whatever it had already grown to — the one number every
dollar is then divided by. ⚠ **A leg's R is windowed but never rebased** — R is normalised to each
trade's own risk, so the scale cannot touch it, which is what makes a windowed row comparable to a
full one. ⚠ **Refused on the `unmeasured` basis** rather than windowing nothing, or an unreplayed
combination would report "this stack did nothing in 2023" instead of "nobody ever ran this".

🔴 **TWO GREEN SUITES EACH HID A MUTATION THAT SURVIVED THEM, ON THE SAME DAY, AND ONE WAS A REAL
DEFECT SITTING IN THE PAGE.** The browser suite asserted on the per-leg R column and nothing else,
so a build that never applied the window to the composed books at all passed — and so did the
Trades column, which was still reading the count the backend stored for the WHOLE run while the R
one cell over was windowed. Two figures touching in one row, one filtered and one not. Separately,
four scaling cases in the node check were written against a window whose scale happened to be
exactly **1**, where *"this field is scaled"* and *"this field is left alone"* are the same
assertion; scaling `r` survived them. **Both were found by running the mutations, not by reading
the tests.** The maps now live in each file's header and both were RUN.

⚠ **Gated in two places, deliberately.** `scripts/check_period_window.mjs` drives the pure module
outside a browser and is **step 10** of `scripts/run_all_tests.sh`; `tests/stack-period-filter.spec.ts`
covers the page. The arithmetic is the half that can be wrong without looking wrong, so it is the
half that does not need the app running.

---

## `useHistoryLimit` takes the run's PARAMS, and omitting them is the defect (2026-08-15)

**A run can load more than its chart timeframe** — `exec_secondary` adds a second feed, **5m
by default since 2026-08-21 and NOT 1m** (`services/run_feeds.py::EXTRA_FEEDS` owns the default)
— and each feed has its own broker floor, so the earliest legal date depends on the PARAMS, not
just the instrument and bar size. The hook takes them and sends the names of every truthy one as
repeated `&flags=`; the backend keeps the ones that mean a feed.

🔴 **AND SINCE 2026-09-01 IT SENDS NUMBERS TOO (`&pv=name:value`), BECAUSE A FLAG STOPPED BEING
ENOUGH.** A feed's timeframe can now come from a run param (the re-entry's fill clock), so names
alone would have bounded every run at the DEFAULT while the run itself loaded something else —
the 2026-08-15 defect one level down, and it would have looked exactly like a date bug again.
⚠ **The rule is unchanged and it is the reason this works: the hook sends EVERYTHING it holds —
every truthy name, every finite number — and the backend keeps only what a feed reads.** A list
of feed params here would be the second claim about one rule, which is the thing this file keeps
warning about. ⚠ **Both are in the query key**, or two runs differing only by fill clock share a
cached floor. ⚠ MEASURED before choosing the shape: 60 numeric params, ~1.4 KB of query string. Backend rules and the incident:
`../backend/CLAUDE.md` → *THE FLOOR IS PER-RUN*.

- ⚠ **Omitting `params` asks the chart-only question and gets a floor that is too EARLY**, which
  renders as a perfectly ordinary date picker offering a date the run will die on. Measured: run
  `50331c7cbe96` was offered 2018-09-13, accepted, and failed at 8% on a 1m feed whose history
  starts 2018-09-14.
- ⚠ **The frontend deliberately carries NO copy of which flags mean a feed.** It sends every
  truthy param name and lets the backend intersect. A copy here is the second claim about one
  rule that this app keeps being bitten by, and a feed added tomorrow would simply never reach
  the picker.
- ⚠ **`flags` is part of the QUERY KEY.** Two runs of one strategy differing only by
  `exec_secondary` have different floors and must not share a cache entry.
- ⚠ **In `RunBacktestModal` the hook sits BELOW the params state**, not beside the other window
  controls, because it depends on them — ticking the secondary moves the earliest date the
  picker accepts.
- ⚠ **`StackConfigModal` passes the UNION of the selected legs' truthy flags.** The legs share
  one window, so it is legal only if EVERY leg can be served. 🔴 **It dropped `exec_secondary`
  in shared mode until 2026-09-10** — the backend stopped pinning it on 2026-09-08 and its floor
  check sees that feed, so the picker offered a start the launch refused.

🔴 **`RerunModal` MOVES an illegal start to the floor and SAYS SO** (`rerun-moved-to-floor`).
This is the Retry path for a failed run, so the run in front of the reader may have failed ON
the floor — and before this the modal re-offered the same illegal date, so Retry could only fail
identically and the only way out was deleting the run. ⚠ **The move is announced, never silent**:
a silent clamp runs a window the reader did not ask for, which is the narrowing this repo refuses
everywhere else. They can type it back; the Rerun button stays disabled until the date is legal,
so nothing is decided for them.

## The strategy page leads with a TL;DR; its stacks list became a filter (2026-09-13)

Aaron: *"when I click on a strategy … it's very technical … I want something that … tells me in
six bullets"*, and of the stacks chips: *"Why do I even care about this? … I don't need that whole
section."*

- **`StrategyDetail` opens on the TL;DR** (`strategy-tldr`) from `Strategy.tldr`. `tldrLines`
  fills `{param}` tokens and drops a bullet whose `show_if` no longer holds, both against the
  schema DEFAULTS — the values the Default column shows. Rules: `../backend/CLAUDE.md` → *The TL;DR*.
- 🔴 **`fillText` (ParamEditor) is THE token rule**, now called by `fillTokens` for option labels
  too. A second filler would be two answers to what `{exec_sl_level}` says.
- **With a TL;DR, the edge and the four steps fold behind "How it works, step by step"**
  (`strategy-flow`); without one they stay open. Say it once — and the steps were what read as too
  technical.
- **The "In N portfolio stacks" section is gone.** The Backtests chip links to
  `/backtests?strategy=<id>` (`strategy-backtests-link`).
- **Backtests has a strategy filter** (`strategy-filter`, `?strategy=`) on Runs and Stacks.
  ⚠ **`setTab` carries ONLY `strategy` across a tab change** — `?account=` must still drop, or the
  stack builder reopens every time Stacks is revisited. ⚠ **A filter that hides every row says
  so**, with *Show all*; "No stacks yet" would be false. ⚠ **A `?strategy=` the list does not hold
  is still offered as an option**, or the select reads "All strategies" over a filtered list.
- ⚠ **No committed browser spec.** Driven by hand in the running app on 2026-09-13; what holds the
  meta files is `backend/tests/test_strategy_tldr.py`.

## The Backtests list and the Backtest detail page — audited 2026-08-06

Aaron asked for an in-depth audit of both pages and then for the fixes. **27 findings; nine real
defects, three of them destructive.** The backend half is in `../backend/CLAUDE.md`; this is the UI
half, and every item shares the shape this folder keeps recording: **not one of them rendered an
error.** A rerun reported success. A caption contradicted the checkbox beside it. A rule silently
skipped the trades that matched two rules.

### The two destructive controls on the list, and the one that did not exist

🔴 **The row Rerun was ONE unconfirmed click, and a rerun replaces the run.** `retry.mutate(...)`
fired on the click, at 13px, inside a row whose own click navigates away, beside the chevron — and
it resets the row in place and discards its result, its charts and its evaluations. The detail page
has opened a modal for the same action since the day it existed. It raises to the page now, which
owns `ConfirmRerunModal`.

🔴 **There was no per-row DELETE at all, and the only reachable delete had no cascade warning.**
`deleteRunId` was never set, so `handleSingleDelete` and `cascadeMessage` were unreachable — and
`cascadeMessage` is the **only** place that says a delete takes attached optimizations, sweeps and
tuning iterations with it. So the one warning that names the blast radius was on the one path
nobody could reach, while the bulk checkbox path — which deletes the most — showed the generic
message. There is a row Delete now, and `bulkCascadeMessage` gives the bulk path the same warning
across the selection.

⚠ **Both raise to the PAGE rather than firing in the row.** The cascade sentence can only be
computed where the optimizations and sweeps lists live, and a row that can start a destructive
mutation on its own is a row one stray click from discarding a result.

**`fmtMoney` gained an `M` step.** `+$14387.5k` — five digits before a thousands suffix, harder to
read than the number it abbreviates, in the column whose whole job is comparing runs at a glance.
The same class as the `FitMoney` fix one page over.

**The bulk-delete failure toast stopped naming a cause it could not know.** It said "not found" for
every failure; a delete can also fail on a foreign key, a 409 or a dead backend, and `api.delete`
has already toasted each real reason. This line is a count, not a diagnosis.

### A caption that contradicted its own checkbox

🔴 **"Bank holidays · on by default"** — left over from when that rule really was hardcoded on, and
still on screen five days after **both** rules were defaulted OFF on 2026-08-01. This repo's
signature defect, sitting on the exact control that was rebuilt to stop it. **If a default changes,
the caption changes in the same commit.**

**`removeNewsChoice` went from `boolean | null` to a plain boolean.** The third state existed to
mean "the reader has not chosen, so fall back to the strategy's `avoid_news`", and that fallback
was removed with the same change. A three-state that only ever resolves one way is a state nobody
can reach, and it reads as though something still depends on it.

### The news filter's two rules did not compose

🔴 `if (in_holiday) {…} else if (in_news) {…}` — one chain doing both the COUNTING and the REMOVING.
A trade that was both took the holiday branch, so **ticking High-impact news with Holidays off left
that trade in the result, silently exempt from the rule you had just switched on.** The `else if`
was written for the counting rule (don't double-count against the total) and leaked into the
removal.

They are separate decisions now: the removal is a plain OR, and since 2026-09-13 each rule also
COUNTS every trade it matches — holiday-wins precedence left the news row's price tag short by the
overlap. The two rows may sum past the pill; the pill's total comes off the kept list. Pinned by a
browser check that tags exactly one trade as both, so the delta it asserts on can only come from
that trade.

### A drawdown percentage withheld with instructions the page gave no way to follow

🔴 Max DD% needs `balance`, which came from the primary evaluated ruleset's `account_size`. With no
evaluation the hero read `—` and the card said **"Set an account balance to measure drawdown as a
percentage"** — while the balance slider renders only when a ruleset default already exists. It
asked for something the page could not accept, and the backend had `max_drawdown_pct` stored on
that row the whole time (the Runs list shows it).

`defaultBalance` falls back to the run's OWN opening balance, recovered from the curve's first
point (`equity - profit`, exact arithmetic — `equity` is cumulative and anchored on it). ⚠ **That
is also the more correct denominator for a self-sizing run**, which compounds off its own deposit
and knows nothing about the account size of a ruleset it was merely graded against; the ruleset
still wins when present, because a prop limit is written against that account. The remaining
fallback message now says a run stored no equity curve, which is the only case left.

🔴 **`rebaseEquity` did not anchor on the opening balance, so it disagreed with the backend.**
`services/metrics.max_drawdown_pct` — what the Runs list renders — PREPENDS the opening balance;
the page started at `balance + profit[0]`. A drawdown is measured from a peak and the account's
first peak is the money it started with, so without the anchor a run that opens with a loss is
measured from a peak already below its own start. ✅ **MEASURED on the shape that decides it — a
run down 40% from $10k that never regains the start reads 25% without the anchor and 40% with it.**
One number, two definitions, two places.

### Three things the cost pill and the failure banner were not saying

🔴 **A partly-priced re-price rendered as "Charging nothing".** If the server returned fewer priced
trades than the curve holds, `view` was null → `active` false → the pill read *Charging nothing*
with the reader's boxes still ticked. The view is right to refuse the short answer — a partly
charged book shown as a charged one is worse than no charge — but the refusal has to reach the
reader. It is a third state now (`partial` / `partialOf`), distinct from `failed` (the server
refused and said why) and from inactive (nothing ticked).

🔴 **The excursion bars were not re-priced**, so the solid net-result core could stick out past its
own translucent favourable halo — which reads as a broken chart. `favorable`/`adverse` shift by the
charge and are then CLAMPED around the new profit, because a halo the result escapes is the one
shape that bar can never draw.

🔴 **`FailureBanner` declared `onRetry` and the page never passed one**, so the banner's Retry
button did not exist — on the one banner a reader is looking at because something failed. It was
wired to `RerunModal` for a standalone run and to the direct re-fire for a sweep child or optimizer
combo, and disabled while that platform held a job (the backend 409s, and a button whose only
outcome is an error toast is not a button).

⚠ **SUPERSEDED 2026-08-15 — THE BANNER HAS NO BUTTON AGAIN, AND THAT IS NOT THE OLD BUG.** The
fix above was right that the control was missing and wrong about where it belonged: the page
HEADER already carries a Retry firing the identical action a few inches up, so the page ended up
with two controls for one destructive action — two places for the disabled state and the period
gate to drift apart. Aaron, from the screen: *"I don't need the double retry buttons, keep the one
outside."* **The banner's job is to say what FAILED.** ⚠ **The props were REMOVED, not left
unused** — a declared-and-never-passed `onRetry` is precisely what made the component look like it
had a button when it did not, so leaving it behind re-arms the original defect. ⚠ **The browser
check was FLIPPED rather than deleted**, and now pins the COUNT (`exactly one Retry, and not on
the banner`) asserting BOTH halves: deleting it would leave nothing stopping the next reader
re-adding the banner button as a fix for the original defect, whose reasoning still reads as sound.

**Worst streak was blank on every per-firm sized view.** `effRun` NULLED `worst_losing_streak` so
it would recompute from the sized daily P&L — but a streak is counted in TRADES and
`FallbackMetrics` deliberately carries no daily answer for it, so it recomputed to nothing. It is
computed from that firm's own equity curve with the exported `worstLosingStreakOf`.

### The running banner — one bar, and its width IS the progress (2026-08-20)

🔴 **A progress bar whose speed is unrelated to the progress is worse than no bar** — it teaches
the reader that the number on it means nothing. `RunningBanner` drew a row of NAMED STAGES as
evenly-spaced dots (`Load bars` / `Replay` / `Results` for a python run, five more for NT8) with
the fill drawn in the connectors between them, and **equal widths carried wildly unequal work**:
loading bars was 0–15% of the run and got half the bar, stepping 156,721 bars was 15–94% and got
the other half. The fill sprinted to mid-screen in seconds and then crawled for minutes, and each
stage change snapped one connector full while the next started at zero — which reads as the bar
falling back. Aaron, 2026-08-20: *"sometimes it shoots up and it shoots back down… very
inconsistent."* It is now ONE bar filled to `pct`, and the stage names are gone — *replay* was
internal vocabulary for stepping the strategy over the bars and said nothing to the person
watching. The words moved to the message line underneath, where a sentence has room to be one.

🔴 **`/lab/progress` IS ONE FILE FOR THE WHOLE APP, and that is the other half of "shoots back
down".** It describes whatever job wrote it last, so a second backtest, an optimization or a sweep
starting anywhere overwrites it — this page stops recognising the job id and used to substitute
zeros: the bar emptied, the message fell back to *Starting…* and the elapsed clock restarted, on a
run that had not slowed down. It now keeps the last report that BELONGED to this run
(`ownProgressRef`), which is the honest answer — a zero there is a statement about somebody
else's job wearing this run's banner. ⚠ **It holds the last real report; it never invents one.**
⚠ **Cleared when a rerun gives the same id a new start time.**

⚠ **The pct itself had to move too, and that is in `backend/CLAUDE.md`** — a bar can only be
proportional if the number behind it is. ⚠ **ONE hold, not two.** The first attempt also held a
running maximum inside the banner, and with both in place **reverting the real fix left every
assertion green** — either mechanism alone kept the bar full. Watched RED by mutation:
`tests/backtests.spec.ts` → *another job stealing the shared progress file cannot empty this bar*
reports `0%` against the old ternary. The bar and its percentage carry `run-progress-fill` /
`run-progress-pct` so the check reads the element it means.

### The finished-run params panel — plain names, three tiers, collapsible (2026-08-20)

🔴 **ITS CLASSIFICATION MOVED OUT TO `components/runSettings.ts` ON 2026-09-06 AND IS NOW SHARED
WITH THE STACK PAGE'S Settings CARD.** That card asks the identical question about each of its
legs and was still printing field names, so the words, the group ORDER and both folds are one
implementation (`buildRunSettingsView`) and each surface owns only its LAYOUT. **Edit the words or
either fold THERE, never here** — the rules below are unchanged and are stated once, under *The
Settings section is ONE card* where the second reader of them lives.

🔴 **It printed FIELD NAMES** — `exec_nogap_arm`, `exec_sl_buf_tk`, `aplus_window` — so the one
surface that records what a finished run actually charged was unreadable without the source open.
Aaron: *"the parameters is the names of the variables in the code… this makes no sense for me when
I look at it."* Every row now shows the words from the strategy's own metadata, and the values with
it: a bool reads as its two option labels (`Arms setups` / `Ignore`) rather than `true`/`false`, and
a number carries its unit (`4320 minutes`, `0 ticks`).

🔴 **A SECOND NAME, `short`, EXISTS BECAUSE THE EDITOR'S LABEL IS WRITTEN TO TEACH.** *Max time:
sweep → SOS (minutes)* is right on the run form and wraps to three lines in a 248px rail, burying
the value under the explanation. Aaron: *"don't be too verbose and try to explain params in the
side bar… they just have to be simple english names."* So `short` is the same setting named in as
few words as possible (*Sweep → SOS window*), read through the exported `shortLabelOf`, and `label`
stays what the editor shows. ⚠ **Authored in the meta, never DERIVED** — stripping parentheses and
units mechanically produces a name nobody chose. ⚠ **Optional everywhere**: no `short` falls back
to `label`, which is what `b_leg` and `bos` do today; `sos_fade` carries one for all 83.
⚠ **Units belong to the VALUE** — the row already renders `4320 minutes`, so a `(minutes)` in the
name says it twice. ⚠ **`strategy_scanner._PARAM_META_KEYS` is a WHITELIST and `short` had to be
added to it** in the same commit, or the key is dropped in silence and the panel looks unchanged.

🔴 **THREE TIERS, EACH DIFFERING IN MORE THAN ONE WAY.** The first pass got the words right and
left them all at one weight and one colour: *"I need the parameter categories and keys to stand out
from the values… right now everything is very flat."* Category = gold, bold, uppercase, tracked,
rule above (the same treatment `ParamEditor`'s compact group headers carry — one shape learned
twice); setting = 10.5px tertiary regular, the question, which should recede; value = 12.5px
semibold primary `tabular-nums`, the answer, and the only thing on the row that differs run to run.
⚠ **Size alone will not carry it at these sizes** — 10px against 12px is nearly invisible in a
248px rail, so every tier moves colour AND weight AND size. The three are constants
(`TIER_CATEGORY` / `TIER_SETTING` / `TIER_VALUE`) so the folds cannot drift from the main list.

🔴 **SECTIONS COLLAPSE, AND THE STATE TRACKS WHAT IS SHUT — NEVER WHAT IS OPEN.** A set of OPEN
groups starts empty, which renders every section collapsed on first paint, and this panel exists to
show at a glance what ran. ⚠ **A shut section still states its COUNT**: a collapsed group with no
number reads as a group with nothing in it, the one thing a record of a run's inputs may never
imply. ⚠ **ONE expand/collapse-all icon in the header, and it offers the action the panel is not
already in** — two buttons leave a dead one on screen at each extreme, and a control that does
nothing when clicked reads as broken rather than as already-done. ⚠ **`allShut` is derived from the
groups that EXIST**, never from a count held beside the set.

🔴 **The `useState` went in BELOW this component's `if (!entries.length) return null` and that is a
crash, not a lint opinion** — *Cannot access 'shutGroups' before initialization*, on the first
click. Caught by driving the real page, not by the typechecker, which was green throughout. Hooks
go above every early return.

⚠ **The two folds were renamed because their headings were internal vocabulary.** *"What does the
settled section even mean?"* — `Settled` is now **Already decided** (*tested, answered, and taken
off the run form; still sent — this run used these*) and `Foundational` is **Instrument & broker**
(*what was traded and how it filled, not how it decided*). Same sets, same rules, said in words.
⚠ **The editor still says "settled" on its own count** — that one can follow if it reads badly
there too, but it is a different surface with a different reader.

🔴 **A SETTING WHOSE PARENT IS OFF DID NOTHING ON THIS RUN, SO IT IS FOLDED AWAY TOO.** Fourteen
secondary re-entry rows sat in the main list on every run with the secondary switched off, and the
same shape repeats through every cascade in the schema (*"if secondary trades is off in the
strategy you DON'T need to show all the params related to it… same goes for anything cascading"*).
Asked of `isOutOfPlay`, exported from `ParamEditor` — a `show_if` that does not hold, or a
`disable_if` that does. ⚠ **The editor asks the same question in two
halves rather than calling this** — `show_if` in `visible`, `disable_if` through `isInert` — because
it reads `show_if` off the RAW value where this resolves `custom_from` first. Since 2026-08-27 both
sides HIDE, so the two agree about the screen; no `show_if` in this repo names a `custom_from`
target today, and the day one does they diverge silently. ⚠ **The PARENT toggle stays in the main list.** A section that empties
completely reads as one that does not apply to this strategy; leaving the switch visible says WHY
the rest is gone. ⚠ **FOLDED, never dropped** — same rule as a settled param. ⚠ **It shares the
"Already decided" fold, so that caption names BOTH reasons a row lands there**, or half its
contents look mis-filed. Measured on the pinned run: the secondary section went 3 rows → 1, entry
zone 4 → 3, sessions 2 → 1, and the fold 26 → 31.

⚠ **Rows are STACKED and grouped**, for the same reason `ParamEditor`'s are: a sentence has no
chance in the ~120px a right-aligned value leaves in a 248px rail, and a truncated label is the
same defect as a field name. Group headings and their ORDER come from the metadata, which is the
order the strategy decides things in. ⚠ **A param with no metadata entry falls back to a prettified
field name rather than vanishing** — this panel is the RECORD of what the run sent, so nothing may
be dropped; `fill_model`, `symbol`, `mintick`, `point_value` and `daily_close_hour_ny` are the live
cases. ⚠ **`fillTokens` runs here too**, against this run's own values, or a toggle reads
`{exec_sl_level}` on the page two clicks from the editor showing `0.886`.

⚠ **`tests/param-gates.spec.ts` asserts on the WORDS** (`RSI length`, not `div_rsi_len`) — every
param in `sos_fade`'s metadata carries a unique short name, so a name still identifies a row
exactly. ⚠ **Its docstring cites the Pine file that greyed the control out first, and that file
MOVED on 2026-09-02** — the `strategy()` sources left `indicators/strategies/` for
`strategies/tradingview/`, so the path was repointed. Nothing the test asserts changed; the
Pine is still where a dead control is decided and this page is still catching up to it. Three checks, all watched RED by mutation: the fold, sections-start-open (flip the set to
track what is open), and the all-in-one icon.

### Efficiency, measured

- **Two `/log` polls during a run, not one.** `RunningBanner` asked for 500 lines and
  `LogsSection` for 200 — `lines` is part of the query key, so that is two cache entries and two
  requests every 2 seconds for the whole run. Both ask for 200. ⚠ If that ever needs to change,
  change both call sites together or the duplicate comes straight back.
- **The run page pulled the whole lab to draw one badge.** `useBacktestRuns()` unfiltered, on the
  argument that it shared the Runs list's cache entry — true while the sidebar held that entry on
  every page, and no longer true since the sidebar moved to `useNavActivity`. It is scoped to
  `source_run_id` now. ✅ **MEASURED: 20.6 KB → 0.002 KB, 10.5 ms → 5.3 ms.** ⚠ Always pass the
  filter — `useBacktestRuns(undefined)` fetches everything.
- **Five backtest hooks toasted their errors twice.** `api.request` already toasts the server's
  `detail`, and `ApiError`'s own docstring forbids toasting on top; the generic message landed
  SECOND and buried the real reason — the history floor's 400 names the earliest date the broker
  has, which is the sentence worth reading. ⚠ The branch in `useTriggerBacktest` could not fire
  anyway: it read `.detail` off an `unknown` that only carries it on an `ApiError`.

### The `python` lock scope never reached the browser

🔴 **`GET /backtests/running-job` named `nt8` and `mt5` and never passed `python`**, and
`RunningJobStatus` declares that field with a `running=False` default — so the omission was silent
and **a python backtest reported its own platform free for its entire run.** Found by DRIVING the
Stop fix against a real backtest, not by reading anything.

Nothing on this side was wrong: `lib/runner.ts` resolves the scope correctly and `runningJobFor`
reads it. But every control gated on it — **the Runs list's Rerun, this page's Retry and Rerun, the
Run modal, the Optimize button** — stayed enabled through a python run, and the backend's gate
(which was never broken) then answered `409`. **A button whose single outcome is an error toast.**
Fixed in the router by DERIVING the response from the scope map; see `../backend/CLAUDE.md`.

⚠ **The lesson for anything reading this shape: a `running: false` from that endpoint was
indistinguishable from a scope nobody had answered for.** The frontend cannot detect the
difference and should not try — but when a gate and its button disagree, suspect the payload before
the predicate.

### `tests/backtests.spec.ts` — 11 checks

**10 of the 11 were WATCHED TO FAIL against the page at HEAD.** The 11th could not be: it needs a
`data-testid` that is part of the fix, so its non-vacuity was established by **MUTATION** — remove
just the `onRetry` prop, confirm red, restore, confirm green.

🔴 **And that test was VACUOUS on its first attempt, which is why the mutation step exists.** It
asserted a page-wide `Retry` button and PASSED against the broken page, because **the page HEADER
carries its own Retry** — the locator was matching a control that was never in question. Same trap
as `page.locator('svg').first()` being the sidebar logo. **A green new test proves nothing until
you have seen it red for the RIGHT REASON.**

⚠ **It asserts on MUTATED state, never on which rows are in the lab today.** The Overview and
Stress Tests suites both broke on the data rather than on the code, and a test that fails on a day
nothing is wrong is indistinguishable from a regression until somebody reads it. ⚠ A cost rule is a
`<button>`, not a `<label>` — `CostRule` renders its own checkbox glyph so a locked row can be
disabled.

## The analysis panels are shared — `components/runAnalysis/` (2026-09-17)

The KPI panel, equity, drawdown, daily P&L and direction charts (`panels.tsx`) and the price-chart
body (`PriceChartView.tsx`) moved VERBATIM out of `pages/BacktestDetail.tsx` so the backtest page,
the stack page and the account Results page use ONE copy. The moved text was diffed against the
original: the only differences are `export` and prettier re-wrapping the lines it lengthened.
`PeriodFilterChip` stays on the backtest page. ⚠ The stack page still builds its run object inline;
`bookRun.ts` is the same arithmetic for the account page, and folding the stack page onto it is a
separate change.

- 🔴 **The equity chart's green/red split is measured on the BALANCE line's values only (2026-09-17).**
  It used every overlay line's values too, so an overlay below the balance (the account page's
  growth line, a stack's strategy leg) moved the split off the start line and painted a winning
  curve red. Seen on the live account page; the shared chart is also the backtest's and the stack's.
