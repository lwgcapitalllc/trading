# Mean Reversion — Python to MQL5 Port
## Build Spec

**For Claude Code.** Translate the existing Python `bot_mean_reversion.py`
into an MQL5 expert advisor (`.mq5`) that runs in MT5's Strategy Tester.
This is the first strategy that will be tested through the M5 MT5 Runner
lab.

Read `algos/docs/BOT_MEAN_REVERSION_GUIDE.md` for the full bot spec
before starting. The Python file at `algos/bots/bot_mean_reversion.py`
is the source of truth for the signal logic.

---

## 0. Communication rules

- Plain English replies. No code blocks unless asked.
- Stop and ask if anything in the Python bot is ambiguous.
- This is a strategy port, not a platform task — `backend/CLAUDE.md`
  and `frontend/CLAUDE.md` are not affected.

---

## 1. What this port delivers

- [ ] `strategies/mt5/MeanReversion.mq5` — production-ready MQL5
  expert advisor
- [ ] Implements the core signal: Bollinger Band + RSI + VWAP confluence
  per the bot guide
- [ ] Foundational config parameters declared with `f_` prefix
  (per M5 convention) — these come from the ruleset at runtime via the
  lab dispatcher
- [ ] Strategy logic parameters declared without prefix — these are
  what the optimizer tunes
- [ ] Compiles cleanly via MetaEditor command-line on the VPS
- [ ] Runs successfully in MT5 Strategy Tester end-to-end on a small
  historical window (1 week of EURUSD H5 bars or similar)

---

## 2. Scope of the port

### What gets ported

The **core signal and exit logic** from `bot_mean_reversion.py`:

- Bollinger Band detection (price outside 2+ standard deviation band)
- RSI confirmation (oversold ≤28, overbought ≥72)
- VWAP deviation confirmation (1.5+ stdev from VWAP)
- Rejection candle confirmation
- Confluence scoring (sum of signals, min 4 to enter)
- Entry execution with computed stop loss and 1R target
- Breakeven move at +0.3R
- Full close at +1R
- Early close on RSI returning to neutral (50 area)
- Tight trail (0.3x ATR) between BE and 1R

### What does NOT get ported

The Python bot has accumulated significant complexity beyond the core
signal that does NOT belong in the MQL5 strategy:

- **AI brain (ML model)** — skip. The strategy is pure rules-based in
  MQL5. ML can be added back later as a separate concern if needed.
- **Multi-instrument scanner** — skip. The strategy runs on whichever
  instrument MT5 attaches it to. The lab handles instrument-level
  testing via separate backtest runs.
- **Volatility filter, dynamic risk engine, correlation guard,
  breakeven gate (Phases 2-5 from the guide)** — skip. These are
  bot-level features that belong in the runtime layer, not the strategy
  itself.
- **Daily/weekly loss caps, max consecutive losses, profit targets** —
  skip in strategy code; these come from foundational config injected
  by the lab dispatcher at backtest runtime via `f_` parameters.
- **Startup reconciliation, JSON file logging, dead zone management,
  weekly cap cooldowns** — skip. These are bot infrastructure, not
  strategy logic.
- **Regime-based size adjustment** — skip. The lab's foundational
  config and the regime filter on the optimizer handle this.

The goal is a **clean, focused strategy file** that does one thing:
implements the mean reversion signal correctly. Everything else is the
lab's job.

---

## 3. Parameter set

### Strategy logic parameters (tunable by optimizer)

```mql5
input int    BBPeriod = 20;            // Bollinger Band lookback
input double BBStdEntry = 2.0;          // BB std dev for entry signal
input int    RSIPeriod = 14;            // RSI lookback
input int    RSIOversold = 28;          // RSI oversold threshold
input int    RSIOverbought = 72;        // RSI overbought threshold
input int    VWAPPeriod = 50;           // VWAP rolling lookback
input double VWAPStdDev = 1.5;          // VWAP deviation threshold
input int    MinConfluenceScore = 4;    // Min confluence to enter
input double BreakevenAtR = 0.3;        // Move to BE at this R
input double FullCloseAtR = 1.0;        // Full close at this R
input double TrailAtrMultiplier = 0.3;  // Trail distance after BE
input int    AtrPeriod = 14;            // ATR lookback for stops/trails
input double AtrSlMultiplier = 1.5;     // Minimum SL distance in ATR
```

### Foundational parameters (injected from ruleset)

```mql5
input double f_AccountSize = -1;             // USD account balance
input double f_RiskPerTradePct = -1;         // % per trade (e.g. 1.0)
input double f_DailyLossCap = -1;            // USD daily max loss
input double f_DailyHaltFraction = -1;       // Halt at this fraction of cap (0-1)
input int    f_MaxConsecutiveLosses = -1;    // Halt after N losses (0 = disabled)
input double f_DailyProfitTarget = -1;       // USD daily target (0 = no target)
input double f_DailyProfitLockPct = -1;      // Fraction of target where risk halves
input string f_EarliestEntryTimeET = "";     // "HH:MM" or "" for no restriction
input string f_LatestEntryTimeET = "";       // "HH:MM" or "" for no restriction
input string f_ForceFlatTimeET = "";         // "HH:MM" or "" for no force flat
input string f_DaysOfWeekAllowed = "";       // "sun,mon,tue,wed,thu,fri,sat" or ""
input double f_CommissionPerSide = 0;
input int    f_SlippageTicks = 0;
```

Defaults of `-1` or empty string are placeholders that get overridden by
the lab's dispatcher. If the strategy runs with these placeholder values
(meaning the lab forgot to inject), the strategy should fail loudly at
init with a clear error message — not silently use bad defaults.

### Behavior of foundational params

The same behavior the NT8 strategies implement after Pass 1:

- Position sizing: `(f_AccountSize * f_RiskPerTradePct / 100) / sl_distance`
- Daily P&L circuit breaker at `f_DailyLossCap * f_DailyHaltFraction`
- Halt after `f_MaxConsecutiveLosses` losses in a row (if > 0)
- Halt if `f_DailyProfitTarget` reached (if > 0)
- Profit lock-in: when day P&L crosses `f_DailyProfitTarget * f_DailyProfitLockPct`,
  cut risk multiplier to 0.5 for the rest of the day
- Trading window: only enter between `f_EarliestEntryTimeET` and
  `f_LatestEntryTimeET`
- Force flat: close everything at `f_ForceFlatTimeET`
- Day filter: only trade on days listed in `f_DaysOfWeekAllowed`

Copy this logic verbatim from the existing NT8 strategies (e.g.
`strategies/ninjatrader/ORB.cs` has it implemented post-Pass-1). Same
behavior, different language.

---

## 4. Implementation notes

### MQL5 vs Python differences to watch

- **MQL5 is statically typed** — declare types explicitly
- **No `numpy` / `pandas`** — use indicator handles (`iBands`, `iRSI`,
  `iATR`) instead of recomputing arrays
- **OnTick vs OnBar** — strategy logic should run on bar close, not on
  every tick. Use `iTime(0, PERIOD_CURRENT, 0)` to detect new bars
- **Time zones** — MT5 uses broker time. ET-based foundational params
  need conversion. The strategy should expose a `BrokerToEtOffset` input
  or auto-detect via the symbol's session info

### VWAP

MQL5 doesn't have a native VWAP indicator. Two options:

- **A. Use a community VWAP indicator** — there are well-tested public
  implementations. Reference one and document the source in the file
  header.
- **B. Hand-roll VWAP** — about 20 lines of MQL5. Cumulative
  `sum(price * volume) / sum(volume)` over a rolling window.

**Recommendation: B.** Cleaner, no external dependency, easy to audit.

### Bollinger Bands

Native — use `iBands(Symbol(), PERIOD_CURRENT, BBPeriod, BBStdEntry, 0, PRICE_CLOSE)`.

### RSI

Native — use `iRSI(Symbol(), PERIOD_CURRENT, RSIPeriod, PRICE_CLOSE)`.

### ATR

Native — use `iATR(Symbol(), PERIOD_CURRENT, AtrPeriod)`.

### Position management

MQL5 trade operations use the `CTrade` class from `Trade/Trade.mqh`. This
provides clean methods for `Buy`, `Sell`, `PositionClose`,
`PositionModify`. Use this, not the older `OrderSend()` API.

### Critical: don't use the old OrderSend() API

MQL5 has two trading APIs. `OrderSend()` is the older one — verbose,
error-prone, but still in many forum examples. The `CTrade` class is
the modern wrapper. Use `CTrade` exclusively.

---

## 5. File header

The `.mq5` file should start with a clean header documenting the
strategy:

```mql5
//+------------------------------------------------------------------+
//|                                              MeanReversion.mq5   |
//|                                                LWG Capital LLC   |
//+------------------------------------------------------------------+
// Mean Reversion strategy — BB + RSI + VWAP confluence
//
// Signal: enter when price is outside BB band, RSI confirms overextension,
//   VWAP deviation confirms, and a rejection candle prints. All checks
//   must align. Confluence scoring: see signal block.
//
// Exits: Breakeven at +0.3R, full close at +1R, early close on RSI
//   neutralization (45-55 range). Tight ATR trail between BE and 1R.
//
// Foundational params (prefixed with f_) come from the ruleset at
// runtime via the LWG Capital backtest lab dispatcher. Do not modify
// these defaults; they will be overridden.
//
// Tunable params (no prefix) are exposed to the optimizer.
//+------------------------------------------------------------------+
#property copyright "LWG Capital LLC"
#property version   "1.0"
#property strict
```

---

## 6. Build order

Strict. Stop and report after each.

1. **Read the source.** Read `algos/bots/bot_mean_reversion.py` carefully.
   Read `algos/docs/BOT_MEAN_REVERSION_GUIDE.md`. Identify the exact
   signal logic and ignore the surrounding bot infrastructure. Report
   back in plain English what you found before writing any MQL5.

2. **Create the file structure.** Empty `strategies/mt5/MeanReversion.mq5`
   with the file header, all parameter declarations (both strategy logic
   and foundational), and stub OnInit/OnDeinit/OnTick functions.
   Confirm it compiles before any logic is added.

3. **Implement indicators.** Add handles for Bollinger Bands, RSI, ATR.
   Implement the hand-rolled VWAP. Test by running on a chart and
   verifying indicator values print correctly to the Experts log.

4. **Implement the signal.** The BB + RSI + VWAP + rejection candle +
   confluence scoring logic. Print signal info to log on each new bar.
   No trade entries yet — just signal detection.

5. **Implement entries.** Position sizing from foundational config,
   stop loss placement (max of BB-derived and ATR-derived), entry via
   `CTrade::Buy()` or `Sell()`. Verify entries fire correctly on signal.

6. **Implement exit logic.** Breakeven at +0.3R, full close at +1R,
   early close on RSI neutralization, ATR trail between BE and 1R.

7. **Implement foundational checks.** All the gating: daily loss cap,
   halt fraction, consecutive losses, profit target, lock-in, hours,
   days. Same behavior as the post-Pass-1 NT8 strategies.

8. **Smoke test in Strategy Tester.** Run the strategy on EURUSD H5 for
   a 1-week historical window. Confirm: no compile errors, no runtime
   errors, some trades are taken, foundational checks trigger correctly
   (test by setting `f_MaxConsecutiveLosses=2` and verifying halt after
   2 losses).

9. **Deploy via the lab's deployment manager.** Once M5 has shipped
   the MT5 deployment path, upload MeanReversion.mq5 via the UI and
   confirm compile success.

10. **Final report.** Plain-English summary of what was built, what
    was skipped, anything from the Python bot that was ambiguous or
    needed interpretation.

---

## 7. What NOT to do

- Don't try to faithfully port every behavior of the Python bot.
  Many of its features are bot-runtime concerns, not strategy concerns.
- Don't add new logic that isn't in the Python bot. This is a port,
  not a redesign.
- Don't include AI/ML scoring. Pure rules.
- Don't write multi-instrument logic. MT5 strategies are
  single-instrument by design — the lab handles instrument iteration.
- Don't reimplement risk engines, correlation guards, breakeven gates.
  These are platform features in the lab.
- Don't optimize for performance prematurely. Focus on correctness.
  MQL5 is fast enough for daily-bar-resolution strategies even with
  unoptimized code.

---

## 8. After this port ships

The Mean Reversion strategy can be:
- Backtested in the M5 MT5 lab against `personal_forex_main` ruleset
- Worthiness-scored to see if it's Tier 1/2/3
- Optimized via the M2 optimizer (regime-filtered if desired)
- Stress-tested via M3
- Regime-analyzed via M4

If grade comes back B+, it becomes a candidate for live forex trading.
If lower, the strategy needs improvements before risking real money.

---

---

## 9. Step 10 — Final report (2026-06-04)

**What was built.** `strategies/mt5/MeanReversion.mq5` — a production-ready MQL5 EA implementing the BB + RSI + intraday VWAP confluence signal. All foundational parameters (risk, hours, force flat, daily caps) are injected at runtime via `f_` params. Strategy logic params are exposed to the optimizer. Compiles 0 errors / 0 warnings via MetaEditor CLI. Smoke-tested on EURUSD H1 (2023-01-02 to 2023-01-08): 3 trades, all exit stages confirmed, broker offset auto-detection confirmed.

**Three deviations from the original spec discovered during review, all approved by user:**

1. VWAP changed from rolling 50-bar mean to intraday (resets at broker midnight, backfills on init). Rolling window is kept only for the std dev scale factor. This matches the Python bot's actual behavior.
2. Broker timezone offset changed from hardcoded to auto-detected via `(TimeTradeServer() - TimeGMT()) / 3600`. Override available via `f_BrokerToEtOffsetHours` (any value other than 99).
3. Consecutive loss counter changed from raw balance comparison to ±0.1R band classification using `g_riskAtEntry`. Prevents commission/spread noise from incorrectly incrementing the streak on breakeven stops.

**Three parameters added beyond the spec, all requested by user:**

- `LondonSessionHoursUTC`, `NewYorkSessionHoursUTC`, `SessionBonusPoints` — session bonus adds +1 to confluence score during active sessions.
- `RSIExtremeOversold = 20`, `RSIExtremeOverbought = 80` — adds +1 to confluence score when RSI is deeply extended.
- `MinimumRR = 1.0` — skips entry if `tp_distance / sl_distance < MinimumRR`.

**What was skipped.** AI brain, multi-instrument scanner, regime-based sizing, volatility filter, correlation guard, breakeven gate, dead zone management, startup reconciliation, JSON logging. All of these are Python bot runtime infrastructure, not strategy logic.

**One outstanding item.** Force flat race condition fix (prevents a spurious "Force flat failed" log line when SL triggers within the same second as force flat time) is applied locally. VPS has the pre-fix version. No trade impact — cosmetic only. Re-upload next time VPS is touched.

**Step 9 (lab deployment)** remains pending M5 shipping the MT5 deployment path.

---

*End of Mean Reversion port spec.*
