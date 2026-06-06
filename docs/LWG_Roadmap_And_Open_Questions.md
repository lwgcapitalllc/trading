# LWG Capital — Roadmap and Open Questions
**Last updated:** 2026-06-06

> Companion to the Project State Snapshot. Hand both to any new Claude.ai chat.

---

## Immediate next work (priority order)

### 1. Validate Pass 1 + Pass 2 + Pass 2.5 + M5 end-to-end

M5, Pass 2.5, Pass 2, and Pass 1 have all shipped. Do the deferred E2E test:
- Deploy ORB, VWAP_MR, Momentum via Strategies-tab Deploy buttons
- Compile via Compile All
- Run a backtest with each against LucidFlex 50k Eval on MNQ
- Run the same backtest against `personal_futures_10k_example` — results should differ
- Run a MeanReversion.mq5 backtest end-to-end on MT5 runner

### 2. Strategy improvements pass

Pick ORB first (M4 showed it has a real edge on TRENDING days).

Add to `strategies/ninjatrader/ORB.cs`:
- **Regime filter** — use the same ADX/ATR/RSI math from `trading/regime/`.
  Only allow trades when classification is TRENDING.
- **Trailing stop after +1R** — move stop to entry at +1R. After +2R, trail
  by 1×ATR.
- **Optional re-entry** — if stopped out at breakeven and signal still valid,
  allow one re-entry per day.

After ORB is updated:
1. Deploy via the one-click Deploy button on the Strategies tab
2. Run through M1 backtest → check worthiness
3. Run through M2 optimizer with `regime_filter="TRENDING"` to find best params
4. Run through M3 stress test → check robustness grade
5. Run through M4 to confirm the regime split still works

Success criteria: grade B or A. If yes → attempt LucidFlex eval. If no →
iterate or move to other strategies.

### 3. M4 diagnostic on VWAP_MR, Momentum, and MeanReversion (MT5)

Run the Performance by Regime breakdown on the other strategies. Identify
which has the strongest single-regime edge as the next strategy to invest
improvement effort in.

---

## Future platform milestones (in order, not yet started)

### Pass 3 — Data Manager (planned)

A UI-based historical data manager that handles per-broker limits, symbol
naming, and incremental refresh. Lives under a new "Data" tab in the command
center.

**Capabilities:**
- Select broker / runner / symbol / timeframe / date range from UI
- Auto-detect broker max history per timeframe (fall back gracefully when
  broker limit is hit — automate what the user just did manually for PU Prime)
- Multi-broker fallback chain (try PU Prime, then IC Markets, then Dukascopy
  CSV, etc.)
- **Canonical symbol naming internally, broker-specific translation at the
  agent boundary.** Lab database uses canonical names like `EURUSD`; each
  agent has its own mapping table to add broker suffixes (`.s` on PU Prime,
  `.raw` on IC Markets, slashes for some CSV vendors, etc.)
- Incremental refresh (fetch only bars since last download, not full
  re-download)
- Quality indicators: bar count vs expected, gap detection, source labeled
  per dataset
- Dukascopy CSV import support for long-history M5 data (free, 10+ years
  for majors)

**Why before M6:** stacking analyses run across more strategies and more
time ranges. The data infrastructure gets hammered. Solid cache layer first.

**Why not now:** The manual `download_mt5_history.py` script is good enough
to unblock immediate strategy testing. Pass 3 adds polish, not capability.

### M6 — Strategy stacking / portfolio construction (was M5)

Combine multiple winning strategies into a portfolio. Naive aggregation —
take daily P&L series from each strategy and combine them. Compute
portfolio-level KPIs: combined Sharpe, correlation matrix, max drawdown of
combined curve, ruleset evaluation on combined daily P&L. New "Portfolios"
tab. Portfolio Detail page with member list, correlation heatmap, combined
equity curve, grade.

**Prerequisite:** at least 2-3 strategies grading B+ individually. Stacking
losers makes a smoother loser, not a winner.

### M7 — Dynamic risk allocation in stacking backtests (was M6)

The realistic stacking simulator. Walks through combined trades
chronologically and respects a shared daily risk budget. Reference
implementation exists in `algos/shared/shared_risk.py` (forex side) — port
into the lab backtest engine.

### M8 — Live deployment integration (was M7)

One-click push from Grade A strategy to NT8 or MT5 live. Command center
triggers the strategy on the right account on the VPS with the right ruleset
parameters injected. Live monitoring exposed in the command center UI.

### M9 — Additional runners as needed

Tradovate, cTrader, or other platforms when need arises. The runner
abstraction is in place from M2; new runners are mostly building a new agent
that speaks the same shape of endpoints.

---

## Smaller items raised but deferred

- **Sniper fib (reverse fib / green zone) component for FFT strategy** —
  explicitly deferred. Will need a separate training session before building.
- **FFT bot rebuild** — a build spec was generated in a prior session for
  Claude Code to implement the structure engine and locked rules. Belongs
  to the algos/forex side, not the command center.
- **News blackout windows in foundational config** — considered, deferred.
  Building a calendar API integration is meaningful work for a nice-to-have.
  Strategy-level feature later if needed.
- **Dynamic per-trade risk scaling (beyond the simple 50% lock-in halving)** —
  considered, deferred. Becomes part of M7's portfolio engine, not
  single-strategy logic.
- **Tradovate as a third runner** — placeholder folder may be created in
  Pass 2.5. No active work planned. Could become M9 if needed.
- **Per-instrument regime threshold tuning** — REGIME_CLASSIFIER.md mentions
  this as future improvement. Not actively planned.
- **Hidden Markov Model regime classifier** — explicitly considered and
  rejected. The rules-based classifier is intentional. Transparency over
  marginal accuracy gains.
- **Port `bot_smc_trend` and `bot_fft` to MQL5** — only Mean Reversion was
  ported in M5. The other two are deferred until/if they're worth
  testing through the lab.

---

## Parallel tracks Aaron is running separately

These have their own dedicated chat sessions and aren't worked on here:

- **Prop firm research workshop** — adding new firms (Apex, TopstepFutures,
  TakeProfitTrader, MyFundedFutures, Tradeify) to the rulesets database
  one at a time. Aaron brings the firm docs, that chat helps select which
  challenge to seed, outputs a Claude Code prompt for seeding.
- **Strategy development discussions** — Aaron is working out strategy
  improvement ideas (ORB regime filter, trailing stops, etc.) in another
  chat. The lab waits to be the testing ground.

Don't proactively bring these up unless Aaron does.

---

## Open architectural questions

These have been discussed but not fully resolved. Surface them if relevant
to the current task; don't proactively re-litigate them otherwise.

- **Personal trading capital amounts and ruleset** — `personal_futures_10k_example`
  and `personal_forex_main` exist as seeds. Aaron will edit them with real
  numbers when ready to trade his own money. Real daily loss cap, weekly
  cap, daily profit goal are TBD.
- **M5 data shortage for low timeframes** — PU Prime demo serves only ~8
  months of M5 data, ~2 years of M15. Limits backtest confidence on
  low-timeframe strategies. Dukascopy CSV import via Pass 3 is the
  long-term answer.
- **Strategy parameter optimization across multiple instruments
  simultaneously** — current optimizer is single-instrument. M4's instrument
  sweep handles multi-instrument discovery but not joint optimization.
- **Long-term: who manages the prop firm accounts when there are 30-50** —
  the platform handles per-account evaluation but the operational layer
  (logging in, tracking which accounts are funded, managing payout requests,
  rotating accounts) isn't built. Out of scope for now but will become real.

---

## Communication rules for new chats

When starting a new chat with this snapshot + roadmap:

1. **Don't re-explain milestones.** They're documented above. Refer back to
   them by name (M3, Pass 1, etc.).
2. **Plain English in all replies.** No verbose framing.
3. **Stop and ask one clear question** when input is needed.
4. **Don't suggest reverting decisions that were already made** — see the
   architectural principles in the snapshot. They're locked.
5. **Update both this roadmap and the snapshot** whenever a milestone ships
   or a major decision is made.

---

*End of roadmap document.*
