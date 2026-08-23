Take one lab run id and answer two questions about it: **is this run TRUE, and was this
configuration WORTH IT.** Never one without the other.

Usage: `/run-audit <run_id>` — optionally `/run-audit <run_id> vs <other_run_id>`.

**Why this exists:** a finished run is the most convincing object in this repo. It has a page,
a chart, a KPI row and a number in dollars, and every one of those renders identically whether
the run is right or wrong. This repo has already shipped a run where **every stored KPI
recomputed to the cent and the page still misled three ways** — a drawdown in dollars only, a
win rate counting breakeven scratches, and a concentration figure answering a different
question from the one its name asks. Arithmetic that reproduces is not verification.

And the second half is what a run is FOR. Turning a feature on and seeing a bigger number is
not evidence the feature paid: with one position slot, **an extra setup does not ADD to the
book, it QUEUES in front of it** — measured on this bot in Run 12, where loosened entries
displaced 17, 36 and 2 real trades and one displaced winner was worth +16.5R on its own.

---

## The rule

**Report nothing you have not either recomputed from the trade list or measured against a
matched control.** A KPI copied out of the runs table is a quote, not a finding.

## Do this

### 1. Read what the run actually IS before reading any number off it

From `command-center/backend/data/lab.db` (`backtest_runs`, joined to `strategies`) and the
report directory `command-center/backend/reports/lab/<run_id>/`:

- instrument, timeframe, window, and **which cost layers were applied** — an empty layer list
  is a FREE run and every dollar in it is a lab figure
- the full parameter dictionary, and specifically **which features were on**
- `sizing_mode`. On a compounding run the dollars are a function of the sequence, so they
  answer a different question from R

State this back in one paragraph before anything else. If the run carried no costs, say so
in the same breath as the first number.

### 2. Recompute the run from its own trade list

`equity_curve.json` carries per-trade `r`, `risk_usd`, `size`, `entry_price`, `exit_price`,
`stop_price`, `mae_price`, `mfe_price`, `kind` and `legs`. Check that they agree with each
other:

- profit equals price move × size, minus costs
- R equals profit ÷ risk
- risk equals size × the distance from entry to the stop that sized it
- each balance equals the one before it plus this trade's profit

**A failure here is a real defect.** Passing proves only that the file is self-consistent —
it says nothing about whether the trade should have happened.

### 3. Run the integrity checks that catch a wrong trade rather than wrong arithmetic

Per trade: exit before entry; stop on the wrong side of entry; the worst price sitting past
the stop that sized it; the best price on the losing side; an outcome label that disagrees
with the sign of the result; two positions open at once when the strategy holds one slot.

⚠ **Three of these have an innocent explanation and you must check WHICH before calling a
bug:**

- **The stop is not managed on the ENTRY bar.** A wick past the stop on the bar the trade
  filled is expected. Look up the entry bar and say whether the extreme fell on it.
- **A wrong-side stop fills at the NEXT bar's open** — the one-bar order delay every fill
  model here is built on. It makes the backtest look slightly worse than reality, which is
  the safe direction. Do not report it as a defect; do report a trade that lost materially
  more than 1R because of it.
- **A trade on a faster fill clock** (a re-entry on the 5m feed) has its extremes measured
  on that feed, so the chart's own candles are the wrong bars to check it against.

### 4. Compare R, never net dollars

Everything that shares a balance compounds, so dollars measure the sequence as much as the
edge. Report sum R, average R, the R drawdown on the cumulative R curve, and the win rate
**with the breakeven-scratch count beside it**. A scratch is neither a win nor a loss and a
win rate that hides them is the metric that already misled here.

### 5. Ask what each feature COST, with a matched control

This is the half that gets skipped. Re-drive the same run with one flag flipped, through the
**same code path the Command Center uses** — `command-center/backend/services/python_runner.py`
`_execute`, given a spec built from the run's own row — so a difference is a difference in the
strategy and not in your re-implementation of it. Write to a scratch job id; never into the
user's report directory.

Then answer, by name:

- **Did the new trades DISPLACE old ones?** Diff the base strategy's trades between the two
  runs on entry time and direction. A setup that merely moved later is a displacement, and it
  is invisible in any count.
- **What did the feature earn, in R, split by the situation it fires in?** A feature with two
  triggers is two features; report them apart.
- **Is any of it one trade?** Drop the single best result and re-total. A leg carried by one
  outlier over six years is a finding, not a strategy.
- **Did it deepen or flatten the drawdown?** Find the worst stretch and list the trades in it
  in order. If the new leg loses alongside the trade it follows, the two are one position at
  a bigger size during exactly the period that matters.

### 6. Say plainly whether it was worth it

One sentence with a number in it. *"It added 34R over six and a half years and made the worst
stretch 0.8R deeper"* is an answer. *"Results were mixed"* is not.

## Report it like this

Open items first, each labelled **still open**, **fixed**, or **just context**. Every number
carries the command that produced it. If a check could not run, say which and why — never let
*cannot check* and *checked and fine* read the same.

## Never

- Quote a KPI from the runs table as a finding
- Report a drawdown in dollars only
- Compare against a run with a different window, timeframe, cost basis, broker or sizing mode.
  If the only available control differs, say so and refuse the comparison rather than
  qualifying it — the difference column becomes the thing that lies
- Write into `reports/lab/<run_id>/` — a run's directory is the run's record
- Call the one-bar stop delay or an entry-bar wick a bug
