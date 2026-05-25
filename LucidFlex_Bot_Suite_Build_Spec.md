# LucidFlex Futures Bot Suite — Build Spec
### Handoff document for Claude Code

This document specifies a backtest engine plus three intraday futures strategies
to be backtested in parallel, then (winners only) built as live bots.

**Read this whole document before writing code. Build in the order given.**

---

## CURRENT STATE — 2026-05-25 (read this first, then the spec)

### Key decision made: NT8 Strategy Analyzer as the backtest engine

The original spec (Part 1) called for a Python backtest engine. That was superseded.
Decision: use NT8 Strategy Analyzer directly. Rationale: NT8 has 5+ years of
tick-accurate historical data already configured, uses the real execution model
(no lookahead possible), and handles commission/slippage natively. The three
strategies were written directly as NinjaScript C# rather than Python first.
The analyze.py script handles verdict logic (KEEP/WARN/DISCARD).

### What is built

| Component | Location | Status |
|-----------|----------|--------|
| ORB_LucidFlex.cs | `markets/futures/lucid_flex/` | ✓ Done — deployed, compiled on VPS |
| VWAP_MR_LucidFlex.cs | `markets/futures/lucid_flex/` | ✓ Done — deployed, compiled on VPS |
| Momentum_LucidFlex.cs | `markets/futures/lucid_flex/` | ✓ Done — deployed, compiled on VPS |
| deploy.py | `tools/` | ✓ Done — SCP + NT8 compile, fully working |
| backtest_config.json | `tools/` | ✓ Done — 6 combos, front-month contracts, 2021–2026 |
| run_all.py | `tools/` | ✓ Done — orchestrator; `--http` flag runs full pipeline via agent |
| vps_backtest_runner.py | `tools/` | ✓ Done — pywinauto NT8 automation |
| analyze.py | `tools/` | ✓ Done — parses CSV, prints KEEP/WARN/DISCARD table |
| vps_agent.py | `tools/` | ✓ Done — Flask HTTP bridge (runs in RDP session on VPS) |

### Session isolation: SOLVED

The session isolation problem is resolved. `vps_agent.py` is a Flask HTTP server
that runs persistently inside the RDP session on the VPS. It bridges the gap:
Mac → SSH tunnel → vps_agent.py → vps_backtest_runner.py → NT8 (all same session).

**To start a run from Mac:**
```
ssh -N -f -L 8765:127.0.0.1:8765 forexvps   # open tunnel (127.0.0.1, not localhost)
curl -X POST http://localhost:8765/run-backtests -H "Content-Type: application/json" -d '{"combo": "ORB_MNQ"}'
curl http://localhost:8765/status             # watch log
python run_all.py --analyze-only --http       # fetch + analyze when done
```

**On VPS (RDP terminal):** `python C:\algos\markets\futures\lucid_flex\tools\vps_agent.py`
Must be started manually in the RDP session each time.

### Historical data: SOLVED — front-month contract notation required

**Root cause found 2026-05-25:** NT8's Strategy Analyzer with a bare master
instrument name (e.g. `MNQ`) looks in `db/minute/MNQ/` — which is empty. The
actual per-quarter data lives in `db/minute/MNQ 03-21/`, `db/minute/MNQ 06-21/`
etc. SA does NOT automatically stitch from those folders when given just `MNQ`.

**Fix:** Use the current front-month contract notation in SA (e.g. `MNQ 06-26`).
With NT8 Global Merge Policy set to **Merge back adjusted**, SA chains backwards
through the rollover dates, loading each quarterly folder in sequence. This
produces a continuous 5-year series from locally downloaded data.

**Required NT8 settings on VPS (one-time, already configured):**
- Tools → Options → Market Data → Global merge policy: **Merge back adjusted**
- Tools → Options → Market Data → Preferred connections – historical → Future: **NinjaTrader**

**Historical data downloaded on VPS (all in `Documents/NinjaTrader 8/db/minute/`):**
- MNQ: 03-20 through 06-26 (quarterly, back to Mar 2020) ✓
- MES: 03-20 through 06-26 (quarterly, back to Mar 2020) ✓
- MGC: 02-20 through 06-26 (bi-monthly, back to Feb 2020) ✓
- MCL: 08-21 through 06-26 (monthly, back to Aug 2021) ✓

**backtest_config.json instruments** (update to next front month after Jun 2026 rolls):
- `MNQ 06-26`, `MES 06-26`, `MGC 06-26`, `MCL 06-26`

**Manual verification (2026-05-25):** Momentum_LucidFlex on MNQ JUN26 ran from
01/04/2021 through 05/24/2026 with hundreds of daily rows — confirms data
stitching works end-to-end before automation is triggered.

### Automation: ready to run combos one at a time

Run combos individually via `--combo` flag (added to full stack: run_all.py →
vps_agent.py → vps_backtest_runner.py). Review each result before triggering the
next. Do NOT batch all 6 until single-combo runs are confirmed stable.

**Bugs fixed so far (all in vps_backtest_runner.py, all deployed):**
- `bar_type` ComboBox removed — NT8 retains the Minute setting between runs
- `OneTradePer` is a CheckBox, not Edit or ComboBox — `set_checkbox()` added;
  fallback chain is now: Edit → CheckBox → ComboBox
- set_edit warning suppressed in fallback chain (was noise, not a real error)
- Strategy class switch crash — stale UIA handle after switching ORB→VWAP caused
  KeyboardInterrupt. Fix: re-acquire SA handle per combo, BaseException catch in
  main loop, 3s sleep after strategy select
- XML read timing — NT8 writes XML async after re-enabling Run button; fixed 2s
  sleep was not enough. Now polls up to 60s for the XML file to appear
- `{ESCAPE}` → `{ESC}` — wrong pywinauto key code caused ValueError on every
  strategy-selection retry, crashing the entire combo (skipping it)
- Instrument notation — bare `MNQ` returns no data; must use `MNQ 06-26`
  (front-month contract) so SA merge policy stitches quarterly history

### Long-term UI vision

React app (local on Mac) → SSH tunnel → vps_agent.py on VPS.
Builds on top of the same HTTP API once the agent is tested end-to-end.
Do NOT build the React app before the agent is tested end-to-end.

### Build order progress (Part 8)

| Step | Status |
|------|--------|
| 1. Build backtest engine | ✓ Done (via NT8 Strategy Analyzer, not Python) |
| 2. Implement 3 strategies | ✓ Done (NinjaScript C#) |
| 3. Deploy + compile on VPS | ✓ Done |
| **4. Run all 6 combos, report results** | **IN PROGRESS — data working (2026-05-25), triggering combos one at a time** |
| 5. Monte Carlo stress test on survivors | Pending backtest results |
| 6. Stop and report stress test results | Pending |
| 7. Live NinjaScript bot (winning strategy only) | Pending |
---

## PART 0 — GROUND RULES (read first)

**The platform decision is settled:** LucidFlex bots run inside **NinjaTrader**, written
in **C# / NinjaScript**. A direct Python-to-Tradovate connection is NOT officially
supported by LucidFlex and will not be used. The existing `bot_futures.py` (Python)
does NOT transfer and should be treated as reference only, not a base.

**However** — the backtest engine (Part 1) should be built in **Python**, run locally,
NOT in NinjaTrader. Reason: Python backtesting is faster to write, faster to iterate,
and easy to test three strategies in parallel. Only the *winning* strategy gets
rewritten as a live NinjaScript bot afterwards. Backtest in Python, deploy in C#.

**The LucidFlex rules every strategy must obey:**
- Futures only (CME micro contracts).
- Intraday only — every position flat by 4:45 PM EST. No overnight. No weekend.
- $50k eval: $3,000 profit target, $2,000 max loss (End-of-Day drawdown), 50% consistency.
- $100k eval: $6,000 profit target, $3,000 max loss (EOD), 50% consistency.
- Funded account: same max loss limit, NO consistency rule, NO daily loss limit.
- Drawdown is **End-of-Day** — measured on closing balance each day, not intraday peak.

**Honest expectations — keep these in mind, do not "optimize them away":**
- No strategy is guaranteed profitable. The backtest decides which (if any) survive.
- Expect at least one of the three strategies to fail the backtest. That is success.
- Backtests on free data filter out bad ideas; they do not prove live profitability.

---

## PART 1 — THE BACKTEST ENGINE (build this first)

A single Python program that tests a strategy against historical futures data and
reports honest performance metrics.

### Requirements

**Data source:** Use free historical data. `yfinance` covers futures proxies:
MNQ→`NQ=F`, MES→`ES=F`, MGC→`GC=F`, MCL→`CL=F`. Daily data is reliable; intraday
from yfinance is limited (~60 days). For deeper intraday history, the engine should
accept a CSV file path as an alternative input so better data can be plugged in later.

**Core behavior the engine MUST get right:**
1. **No lookahead bias.** A signal computed from a bar may only be acted on at the
   NEXT bar's open. Shift all signals forward one bar. This is the single most
   important correctness rule. A backtest with lookahead looks great and is worthless.
2. **Realistic costs.** Model commission per contract per side AND slippage. These
   are config values. A backtest without costs is fiction.
3. **Intraday session rules.** Enforce a session window. Force-close any open
   position by a configurable time (default 3:30 PM EST — buffer before 4:45 hard close).
4. **Position sizing** from a risk percentage and stop distance — see Part 5.

### KPIs the backtest MUST output

Per strategy, per instrument, AND combined. These are grouped by importance —
the prop-specific KPIs at the top matter MORE than the standard ones for this
project, because they directly predict eval pass/fail.

**TIER 1 — Prop-specific KPIs (most important — these decide pass/fail):**
- **Max drawdown vs limit** — the worst peak-to-trough loss, AND an explicit
  PASS/FAIL flag: does it stay under the LucidFlex max-loss limit ($2,000 on
  $50k / $3,000 on $100k)? A strategy that breaches this FAILS regardless of return.
- **Simulated eval result** — run the strategy through the actual eval rules:
  did it reach the profit target ($3,000 / $6,000) BEFORE ever breaching the
  drawdown limit? Output: "would have passed" / "would have failed", and if
  passed, how many trading days it took.
- **Daily P&L distribution** — list/histogram of each day's profit and loss.
  Needed to judge the 50% consistency rule: would any single day have been
  more than 50% of total profit? Flag it if so.
- **Worst day / worst losing streak** — largest single-day loss, and the longest
  run of consecutive losing days. Tells you the realistic pain to expect.

**TIER 2 — Edge-quality KPIs (is the edge real?):**
- Win rate, profit factor
- Average win, average loss, average win:loss ratio
- Total number of trades (too few = result can't be trusted)
- Expectancy per trade (average $ won/lost per trade after costs)

**TIER 3 — Standard performance KPIs:**
- Total return, CAGR
- Sharpe ratio, Sortino ratio
- Average trade duration
- Equity curve (matplotlib plot saved to file)

**Backtest period:** As many years as the data allows. Must span trending AND
choppy/sideways periods — not one lucky stretch.

**Output:** A clear results table (one row per strategy per instrument) plus
equity curve plots. Save results to a file so they can be reviewed.

### Strategy interface

Design the engine so a strategy is a self-contained function/class with a standard
shape: it receives price bars and returns entry/exit signals. All three strategies
below plug into the same engine. This makes parallel testing trivial — run all
three through the same engine, compare the output tables side by side.

---

## PART 2 — STRATEGY 1: Opening Range Breakout (ORB)

**Idea:** The first part of the US session often sets the day's direction. Trade a
breakout beyond the opening range.

**Instrument (primary):** MNQ (Micro Nasdaq). Also test on MES.

**Rules:**
- At US cash open (9:30 AM EST), record the high and low of the first 15 minutes
  — this is the "opening range."
- Entry long: price breaks above the opening range high. Entry short: price breaks
  below the opening range low. Enter on the bar AFTER the breakout bar closes.
- One trade per direction per day maximum. Optional: one trade per day total
  (config flag).
- Stop loss: the opposite side of the opening range.
- Take profit: a configurable multiple of the opening range width (default 1.5x).
- Time exit: force-close by 3:30 PM EST regardless of P&L.

**Config-tunable parameters:** opening range minutes (default 15), take-profit
multiple (default 1.5), max trades per day, instrument.

**Best conditions:** trending, news-driven, volatility-expansion days.
**Worst conditions:** quiet, rangebound days (false breakouts).

---

## PART 3 — STRATEGY 2: VWAP Mean Reversion

**Idea:** Intraday price oscillates around VWAP (volume-weighted average price).
When it stretches too far, it tends to snap back.

**Instrument (primary):** MES (Micro S&P). Also test on MGC.

**Rules:**
- Compute intraday VWAP from the session's bars.
- Compute the standard deviation of price from VWAP.
- Entry long: price drops a configurable number of standard deviations BELOW VWAP
  (default 2.0). Entry short: price rises that many std devs ABOVE VWAP.
- Enter on the bar after the condition is met.
- Stop loss: a further extension away from VWAP (default 1 additional std dev).
- Take profit: price returns to VWAP (or a configurable fraction of the way back).
- Time exit: force-close by 3:30 PM EST.

**Config-tunable parameters:** std-dev entry threshold (default 2.0), std-dev stop
extension (default 1.0), take-profit target (VWAP touch vs partial), instrument.

**Best conditions:** rangebound, choppy, low-news days.
**Worst conditions:** strong trend days (fades a move that keeps going).

---

## PART 4 — STRATEGY 3: Intraday Momentum Pullback

**Idea:** In an intraday trend, enter on small pullbacks rather than chasing.

**Instrument (primary):** MGC (Micro Gold). Also test on MCL.

**Rules:**
- Define intraday trend: price above a rising short-period moving average
  (default 20-period on 5-minute bars) = uptrend. Below a falling MA = downtrend.
- In an uptrend: wait for price to pull back and touch the moving average, then
  enter long when price resumes in the trend direction (a bar closes back up).
- Opposite logic for downtrends.
- Enter on the bar after the resumption bar closes.
- Stop loss: below the pullback low (long) / above the pullback high (short).
- Take profit: a configurable reward:risk multiple (default 2.0), OR a trailing stop.
- Time exit: force-close by 3:30 PM EST.

**Config-tunable parameters:** MA period (default 20), reward:risk target (default
2.0), trailing-stop on/off, instrument.

**Best conditions:** steady intraday trends.
**Worst conditions:** choppy days with no clean trend.

---

## PART 5 — RISK & POSITION SIZING (applies to ALL strategies)

This is what keeps a LucidFlex account alive. Non-negotiable.

- **Risk per trade:** 0.25%–0.5% of account size. Config value. Default 0.5%.
  On a $50k account, 0.5% = $250 risk per trade. Do NOT use higher numbers.
- **Position size formula:** dollar risk ÷ (stop distance in points × point value
  of the contract). Round DOWN to whole contracts. Start with micro contracts only.
- **Self-imposed daily stop:** if the day's losses reach a config threshold
  (default: 60% of the way to the EOD max-loss limit), the bot stops trading for
  that day. LucidFlex funded has no daily loss limit, so this is our own guardrail
  protecting the End-of-Day drawdown.
- **Consistency awareness (eval mode only):** the bot should track cumulative
  profit and, when a single day's profit is approaching 50% of total profit,
  reduce or stop trading for that day so the consistency rule is not breached.

---

## PART 6 — THE EVAL / FUNDED CONFIG TYPE (requested feature)

Each bot reads a config file. The config MUST include a `mode` field with two
valid values: `"eval"` and `"funded"`. The bot changes behavior based on it.

```
{
  "mode": "eval",                    // "eval" or "funded"
  "account_size": 50000,
  "profit_target": 3000,             // eval only — informational in funded
  "max_loss_limit": 2000,            // the EOD drawdown limit
  "consistency_pct": 50,             // eval only
  "risk_pct_per_trade": 0.5,
  "daily_stop_pct_of_maxloss": 60,   // self-imposed daily halt
  "session_close_et": "15:30",       // force-flat time
  "instrument": "MNQ",
  "strategy": "opening_range_breakout",
  "commission_per_side": 0.0,        // fill with Lucid's real number
  "slippage_ticks": 1
}
```

**How `mode` changes behavior:**

| Behavior | `eval` mode | `funded` mode |
|---|---|---|
| Consistency rule | ENFORCED — throttle/stop a day nearing 50% of total profit | IGNORED — Lucid funded has no consistency rule |
| Profit target | Bot tracks progress to target; can ease off near the end | No fixed target — bot keeps trading steadily |
| Daily self-stop | Active (protects EOD drawdown) | Active (protects EOD drawdown) |
| Risk per trade | Conservative (default 0.5%) | Conservative (same or lower) |

The bot must NEVER assume which mode it is in — it reads `mode` from config and
behaves accordingly. One codebase, two modes, switched by one config field.

This applies to BOTH the Python backtest engine (so it can simulate eval vs funded
behavior) AND the eventual NinjaScript live bot.

---

## PART 7 — MONTE CARLO STRESS TEST (second filter, after backtest)

A plain backtest shows what happened on ONE historical path. A strategy can look
good simply because it got lucky on that one path. The stress test answers a
different question: **"across thousands of plausible alternate outcomes, how bad
can it realistically get?"** For a prop account, the worst-case drawdown is
exactly what decides whether an eval fee is safe to spend.

**When to run it:** AFTER the backtest, on SURVIVORS ONLY. A strategy that already
failed the basic backtest does not get stress tested — it's already dead. Pipeline:
backtest → kill failures → stress test survivors → review.

**Important — do NOT reuse the existing `stress_test_suite.py` in the repo.** That
file uses made-up, hardcoded win rates. A valid stress test must use the REAL trades
produced by the real backtest of the real strategy. Build this fresh.

### What the stress test must do

Take the actual list of closed trades from a strategy's backtest, then generate
many thousands of alternate scenarios. Use both of these methods:

1. **Trade-order reshuffle:** Randomly reshuffle the sequence of the real trades
   thousands of times (e.g. 10,000 runs). Same trades, different order. This shows
   how much the result depended on lucky sequencing — e.g. whether the losses
   happened to cluster at a bad time.
2. **Resampling with replacement (bootstrap):** Build alternate trade histories by
   randomly drawing trades (with replacement) from the real set. This simulates
   "what if the strategy ran over a different but statistically similar period."

### KPIs the stress test must output

- **Distribution of max drawdown** across all runs — median, and the worst 5% and
  worst 1% (95th/99th percentile). The worst 1% drawdown is the key number:
  if even the worst 1% stays under the LucidFlex limit, the strategy is robust.
- **Probability of breaching the LucidFlex max-loss limit** — across all runs,
  what % would have blown the eval? This should be very low (ideally near 0%).
- **Probability of passing the eval** — across all runs, what % reached the
  profit target without breaching? 
- **Distribution of final P&L** — median, 10th percentile, worst case.
- **Equity curve fan chart** — plot many simulated equity paths on one chart so
  the range of outcomes is visible at a glance.

### How to read it

- Worst 1% drawdown stays under the limit → strategy is robust. Good sign.
- Worst 1% drawdown breaches the limit → the strategy passed the plain backtest
  by luck. It is fragile. Do NOT take it to a real eval.
- A strategy must survive BOTH the backtest AND the stress test to advance.

---

## PART 8 — BUILD ORDER FOR CLAUDE CODE

1. ✓ **DONE** — Build the backtest engine. Implemented via NT8 Strategy Analyzer
   (not Python — see CURRENT STATE section for rationale).
2. ✓ **DONE** — Implement all three strategies. Written as NinjaScript C#.
3. ✓ **DONE** — Deploy + compile on VPS. All 6 combos configured in backtest_config.json.
4. **BLOCKED → IN PROGRESS** — Run all 6 combos, stop and report results.
   Blocked by Windows session isolation. Fix: build vps_agent.py (see CURRENT STATE).
   Once unblocked: `python3 tools/run_all.py --auto-run` runs the full pipeline.
5. **PENDING** — Build Monte Carlo stress test (Part 7) on survivors only.
   Do not start until backtest results are reviewed.
6. **PENDING** — Stop and report stress test results. Owner reviews.
7. **PENDING** — Live NinjaScript bot for the winning strategy only.
   Do not build until stress test results are reviewed.

Steps 1–3 done. Step 4 is the current task. Step 5 follows backtest review.
Step 7 comes last, after stress-test review. Do each, then stop and report.

---

## PART 9 — WHAT NOT TO DO

- Do NOT skip the lookahead-bias protection. Signals act on the next bar's open.
- Do NOT omit commission and slippage. A costless backtest is fiction.
- Do NOT tune parameters to make the backtest look good (overfitting). Use the
  default parameters given here.
- Do NOT reuse the old `stress_test_suite.py` — it uses fake hardcoded win rates.
  The stress test must use the real trades from the real backtest.
- Do NOT stress test a strategy that failed the basic backtest — it's already dead.
- Do NOT build the live NinjaScript bot before BOTH the backtest AND stress test
  results are reviewed by the owner.
- Do NOT use risk levels above 0.5% per trade.
- Do NOT claim a strategy "works" — report the numbers and let the owner judge.
