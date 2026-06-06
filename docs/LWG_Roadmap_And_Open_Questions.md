# LWG Capital — Roadmap and Open Questions
**Last updated:** 2026-06-06

> Companion to the Project State Snapshot. Hand both to any new Claude.ai chat.

---

## Immediate next work (priority order)

### 1. Validate the full platform end-to-end (deferred from M5)

M5, Pass 2.5, Pass 2, and Pass 1 have all shipped. Do a full E2E validation before investing in strategy improvement:
- Deploy ORB, VWAP_MR, Momentum via the Strategies-tab Deploy buttons
- Compile via Compile NT8
- Run a backtest with each against LucidFlex $50k Eval on MNQ
- Run the same backtest against `personal_futures_10k_example` — foundational config should differ between the two
- Run one MeanReversion backtest on MT5 runner (EURUSD or GBPUSD) end-to-end

### 2. Strategy improvements pass — ORB first

M4 showed ORB has a real edge on TRENDING days. That's the entry point for improvement. Add to `strategies/ninjatrader/ORB.cs`:
- **Regime filter** — use the same ADX/ATR/RSI signals from `trading/regime/`. Only allow trades when classification is TRENDING.
- **Trailing stop after +1R** — move stop to entry at +1R, then trail by 1×ATR after +2R.
- **Optional re-entry** — one re-entry per day if stopped out at breakeven and signal is still valid.

After updating: Deploy → backtest → check worthiness → optimize with `regime_filter="TRENDING"` → stress test. Success criteria: grade B or A. If yes, attempt LucidFlex eval.

### 3. Baseline runs on VWAP_MR and Momentum

Both NT8 strategies have zero or minimal runs. Run the M4 regime diagnostic on both — identify which has the strongest single-regime edge and what instrument shows the most promise. That determines which strategy gets improvement effort after ORB.

### 4. MT5 strategy development

`MeanReversion.mq5` is smoke-tested but not optimized. Once the NT8 improvement loop is established and the E2E validation passes, run the MeanReversion strategy through a sweep on multiple forex pairs and optimizer to see if it has a viable edge.

---

## Future platform milestones (in order, not yet started)

### Pass 3 — Data Manager (planned)

A UI-based historical data manager that handles per-broker limits, symbol naming, and incremental refresh. Lives under a new "Data" tab in the command center.

Capabilities: select broker/runner/symbol/timeframe/date range; auto-detect broker max history per timeframe; multi-broker fallback chain (PU Prime → IC Markets → Dukascopy CSV); canonical symbol naming internally with broker-specific translation at the agent boundary; incremental refresh; quality indicators (bar count vs expected, gap detection, source labeled per dataset); Dukascopy CSV import for long-history M5 data (free, 10+ years for majors).

**Why before M6:** stacking analyses run across more strategies and more time ranges, hammering the data infrastructure. Solid cache layer first. **Why not now:** the manual `download_mt5_history.py` script unblocks immediate testing. Pass 3 adds polish, not new capability.

### M6 — Strategy stacking / portfolio construction

Combine multiple winning strategies into a portfolio. Take daily P&L series from each strategy and aggregate them. Compute portfolio-level KPIs: combined Sharpe, correlation matrix, max drawdown of combined curve, ruleset evaluation on combined daily P&L. New "Portfolios" tab with portfolio detail page: member list, correlation heatmap, combined equity curve, grade.

**Prerequisite:** at least 2-3 strategies individually grading B+. Stacking losers makes a smoother loser.

### M7 — Dynamic risk allocation in stacking backtests

The realistic stacking simulator. Walks through combined trades chronologically and respects a shared daily risk budget. Reference implementation exists in `algos/shared/shared_risk.py` (forex side) — port the logic into the lab backtest engine.

### M8 — Live deployment integration

One-click push from a Grade A strategy to NT8 or MT5 live. Command center triggers the strategy on the right account on the VPS with the right ruleset parameters injected. Live monitoring surfaced in the command center UI.

### M9 — Additional runners as needed

Tradovate, cTrader, or other platforms when need arises. The runner abstraction is in place from M2; new runners are mostly building a new agent that speaks the same endpoint shape.

---

## Smaller items raised but deferred

- **NT8 auto-start on VPS reboot** — documented in `strategies/CLAUDE.md` as an operational gap. MT5 bots use `SYS_STARTUP` (runs whether logged on or not); NT8 has no equivalent. A VPS reboot requires manual RDP to restart NT8 and reload strategies. Fix is a scheduled task at startup — not built yet.
- **Sniper fib (reverse fib / green zone) component for FFT strategy** — explicitly deferred. Needs a dedicated training session before building. Belongs to the algos/forex side.
- **FFT bot rebuild** — build spec was generated. Belongs to `algos/`, not command center. Not active.
- **News blackout windows in foundational config** — considered, deferred. Calendar API integration is meaningful work for a nice-to-have.
- **Dynamic per-trade risk scaling** — deferred. Becomes part of M7's portfolio engine.
- **Tradovate as a third runner** — placeholder folder exists. No active work planned.
- **Per-instrument regime threshold tuning** — noted in `REGIME_CLASSIFIER.md` as a future improvement. Not actively planned.
- **Hidden Markov Model regime classifier** — explicitly rejected. Rules-based classifier is intentional. Transparency over marginal accuracy gains.
- **Port `bot_smc_trend` and `bot_fft` to MQL5** — only MeanReversion was ported in M5. The other two are deferred until/if they're worth testing through the lab.
- **`correlation_table.py`** — was added in the M3 stress-test commit as a helper for correlated-instrument notes on StrategyDetail. It was deleted at some point without a corresponding commit and nothing currently imports it. If the correlated instrument feature is wanted, this file needs to be restored or replaced.

---

## Parallel tracks Aaron is running separately

These have their own dedicated chat sessions and are not worked on in the main platform thread:

- **Prop firm research workshop** — adding new firms (Apex, TopstepFutures, TakeProfitTrader, MyFundedFutures, Tradeify) to the rulesets database one at a time. Aaron brings the firm docs; that chat helps select which challenge to seed and outputs a Claude Code prompt for seeding.
- **Strategy development discussions** — working out improvement ideas for ORB (regime filter, trailing stops, etc.) in a planning chat. The lab is the testing ground once the design is settled.

Don't proactively bring these up unless Aaron does.

---

## Open architectural questions

These have been discussed but not fully resolved. Surface them if relevant to the current task; don't proactively re-litigate them otherwise.

- **Personal trading capital and rulesets** — `personal_futures_10k_example` and `personal_forex_main` exist as seeds. Aaron will edit them with real numbers when ready to trade his own money. Real daily loss cap, weekly cap, and daily profit goal are TBD.
- **M5 data shortage for low timeframes** — PU Prime demo serves only ~8 months of M5 data and ~2 years of M15 data. This limits backtest confidence on low-timeframe strategies. Dukascopy CSV import via Pass 3 is the long-term answer.
- **Strategy parameter optimization across multiple instruments simultaneously** — the current optimizer is single-instrument. The instrument sweep handles multi-instrument discovery but not joint optimization. No solution designed yet.
- **Long-term operational layer for 30-50 funded accounts** — the platform handles per-account evaluation but the operational layer (logging in, tracking which accounts are funded, managing payout requests, rotating accounts) isn't built. Out of scope for now.
- **`completed_at` column on optimizations** — all three existing optimization rows have `completed_at = NULL` in the database even for completed optimizations. The `complete_optimization()` function in `lab_db.py` sets this field, so newly completed optimizations should be fine. Existing rows appear to have been affected by the `_migrate_optimizations_nullable_ruleset()` table-recreation migration. Not causing visible errors but worth noting.

---

## Communication rules for new chats

When starting a new chat with this snapshot + roadmap:

1. Don't re-explain milestones. They're documented above. Refer back to them by name (M3, Pass 1, etc.).
2. Plain English in all replies. No verbose framing.
3. Stop and ask one clear question when input is needed.
4. Don't suggest reverting decisions that were already made — see the architectural principles in the snapshot. They're locked.
5. Update both this roadmap and the snapshot whenever a milestone ships or a major decision is made.

---

*End of roadmap document.*
