# M5 — MT5 Runner
## Build Spec

**For Claude Code.** Fifth milestone of the command center lab. Brings
forex into the lab via a second runner (MT5) that sits alongside the
existing NinjaTrader runner. Same backend, same UI, same evaluation
pipeline — just a different backtest engine and different strategy file
format.

Read `backend/CLAUDE.md`, `frontend/CLAUDE.md`,
`Command_Center_Backtest_Engine_Design.md`, and
`strategies/CLAUDE.md` first.

---

## 0. Communication rules (carried)

- Plain English replies. No code blocks unless asked.
- One clear question with concrete options when input needed.
- Update CLAUDE.md in the same session as approved changes.
- This IS a new milestone — M5 in the build order.

---

## 1. What M5 delivers (acceptance checklist)

- [ ] New `mt5_agent.py` running on the VPS — sister to the existing
  `nt8_agent.py` for NT8. Exposes the same shape of endpoints but drives
  MT5 instead of NT8.
- [ ] Backend dispatcher routes by the `runner` field on strategies:
  `ninjatrader` strategies go to the NT8 agent, `mt5` strategies go to
  the MT5 agent. Unified backtest pipeline behavior.
- [ ] MT5 Strategy Tester driven via the `MetaTrader5` Python library —
  no pywinauto. Cleaner than the NT8 path.
- [ ] OHLC data for forex regime classification fetched from MT5 directly
  (H1 + H4 timeframes) via the same Python library. yfinance fallback
  only if MT5 connection fails.
- [ ] At least one MQL5 strategy in `strategies/mt5/` for end-to-end
  testing — initially the ported Mean Reversion strategy from a separate
  build effort.
- [ ] Forex rulesets seeded: at minimum `personal_forex_main` and
  `personal_forex_demo` as `ruleset_type = "personal"`. No prop firm
  rulesets seeded for forex.
- [ ] Forex instruments seeded for use: XAUUSD, XAGUSD, EURUSD, GBPUSD,
  GBPJPY, USDJPY, AUDUSD, USDCAD, EURGBP, NAS100. Broker-suffix handling
  documented.
- [ ] UI shows runner badges on strategies (NinjaTrader green / MT5 blue)
  and adds a market filter (futures / forex / all) across the lab tabs.
- [ ] Regime classifier called with H1 + H4 for MT5 strategies, daily for
  NT8 strategies — driven by strategy.runner.
- [ ] Pass 2's deployment manager extended: `strategies/mt5/` files
  deploy to MT5's `MQL5/Experts/` folder on the VPS. Compile is via
  MetaEditor (or MT5's own compiler) instead of NT8's F5.
- [ ] All four CLAUDE.md files + design doc updated. The new
  `M1-M5 retrospective` reflects this scope.

---

## 2. The MT5 agent — `mt5_agent.py`

### What it is

A Python service running on the VPS, listening on a port (suggest 8766
to avoid conflict with NT8 agent's 8765). Uses the official `MetaTrader5`
package to drive MT5 programmatically.

### Why this is easier than the NT8 agent

MetaTrader5 has a real Python API. No window-driving, no keyboard
shortcuts, no fragility. Functions like:
- `mt5.initialize()` — connect to running MT5 instance
- `mt5.history_select(date_from, date_to, symbol)` — fetch historical data
- `mt5.copy_rates_from(...)` — get OHLC bars
- Backtest control via writing `.set` files and triggering Strategy Tester

The one wrinkle: MT5's Strategy Tester doesn't have a fully programmatic
trigger out of the box. There are two patterns:

**A. Use MT5's command-line Tester mode** — MT5 can be launched with
`/portable /config:file.ini` arguments that include tester config. Runs
headless, writes results to disk, exits.

**B. Use a Tester EA wrapper** — write a tiny "wrapper EA" that takes
configuration from a JSON file, runs the strategy in normal-EA mode
on historical data, writes results.

**Recommendation: A.** It's the standard pattern, well-documented in MT5
community resources. The Python agent generates an `.ini` config file,
launches `terminal64.exe` with that config, waits for the result file
to appear, parses it, returns to the backend.

### Endpoints (must mirror the NT8 agent's shape so the backend
dispatcher is symmetric)

```
GET   /status                            → is MT5 alive? are credentials set?
POST  /backtests                         → trigger a backtest
GET   /backtests/{job_id}                → poll status
GET   /backtests/{job_id}/results        → fetch final results JSON
GET   /historical_data                   → daily/H1/H4 OHLC
GET   /files/strategies                  → list .mq5 / .ex5 files in MT5 Experts folder
POST  /files/strategies/{filename}       → upload a .mq5 file
DELETE /files/strategies/{filename}      → delete
POST  /compile                           → trigger MQL5 compile via MetaEditor
GET   /compile/{job_id}                  → poll compile status
```

The shape matches the NT8 agent. The backend doesn't care which agent it's
talking to — it sees the same endpoints either way.

### MT5 Strategy Tester output

When the Tester completes, MT5 writes a report file. The agent parses
this and produces the same shape of result the backend expects from the
NT8 agent. Specifically:

- Trade list (entry/exit/PnL per trade)
- Equity curve (running balance)
- Daily PnL aggregation
- Standard KPIs (net PnL, profit factor, win rate, max drawdown, sharpe)

The backend's existing `BacktestResult` shape is reusable. The mt5_agent
just produces it in the same format.

### Connection details

Default port: 8766. SSH tunnel from Mac to VPS: `localhost:8766`.

The Mac backend has two agent clients now:
- `services/nt8_agent_client.py` (rename from `nt8_agent_client.py` — clearer)
- `services/mt5_agent_client.py` (new)

Both implement the same interface. Dispatcher picks one based on
strategy.runner.

---

## 3. Backend changes

### Dispatcher refactor

The existing dispatcher in `services/nt8_agent_client.py` (or wherever it lives
now after Pass 1) needs to become a clean router:

```python
def get_agent_client(strategy: Strategy) -> AgentClient:
    if strategy.runner == "ninjatrader":
        return nt8_agent_client
    elif strategy.runner == "mt5":
        return mt5_agent_client
    else:
        raise ValueError(f"Unknown runner: {strategy.runner}")
```

Every place that currently calls the NT8 agent client directly gets
routed through this dispatcher. The dispatcher signature is the same
for both runners.

### Forex rulesets — schema additions

The `rulesets` table needs a few additions to support forex correctly:

```sql
ALTER TABLE rulesets ADD COLUMN market TEXT NOT NULL DEFAULT 'futures';
-- values: 'futures' | 'forex' | 'mixed'

ALTER TABLE rulesets ADD COLUMN drawdown_unit TEXT NOT NULL DEFAULT 'usd';
-- values: 'usd' | 'percent' — forex prop firms often use percentages
-- For personal accounts you can pick either
```

Existing futures rulesets get `market = 'futures'` and
`drawdown_unit = 'usd'` (backfill).

### Forex rulesets — seed data

Seed two personal-type rulesets:

```python
{
  "id": "personal_forex_main",
  "name": "Personal Forex Main Account",
  "ruleset_type": "personal",
  "market": "forex",
  "drawdown_unit": "usd",
  "account_size": 10000,        # placeholder — user edits
  "daily_loss_cap": 200,         # placeholder
  "weekly_loss_cap": 700,        # placeholder
  "daily_profit_target": 150,    # placeholder
  "daily_profit_lock_pct": 0.80,
  "risk_per_trade_pct": 1.0,
  "max_consecutive_losses": 3,
  "earliest_entry_time_et": null,    # FX runs 24h — no restriction
  "latest_entry_time_et": null,
  "force_flat_time_et": null,        # MT5 strategies usually flat by session end
  "days_of_week_allowed": ["sun","mon","tue","wed","thu"],  # FX is Sun open - Fri close
  "allowed_instruments": ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "GBPJPY",
                          "USDJPY", "AUDUSD", "USDCAD", "EURGBP", "NAS100"],
  "max_contracts": {"any": 5},   # adjust to your actual position size cap
  "platform_support": ["MT5"],
  "default_commission_per_side": 0.0,  # FX is typically spread-based; placeholder
  "default_slippage_ticks": 1,
  "description": "Personal forex trading account. Edit with real numbers."
},
{
  "id": "personal_forex_demo",
  "name": "Personal Forex Demo Account",
  "ruleset_type": "demo",
  "market": "forex",
  ...same shape, marked as demo
}
```

User edits these via the Ruleset Edit modal once real numbers are
decided.

### Instrument metadata table

The lab needs to know per-instrument facts like tick size, pip value,
broker suffix. Add:

```sql
CREATE TABLE instrument_metadata (
  symbol            TEXT PRIMARY KEY,
  market            TEXT NOT NULL,         -- 'futures' | 'forex'
  display_name      TEXT NOT NULL,
  tick_size         REAL,
  point_value_usd   REAL,
  broker_suffix     TEXT,                  -- e.g. '.s' for some brokers
  default_session   TEXT,                  -- 'london' | 'newyork' | '24h'
  notes             TEXT
);
```

Seed entries for all the forex instruments above and the existing futures
instruments. This becomes the single source of truth for instrument facts
across the lab.

### OHLC fetcher update

`services/ohlc_fetcher.py` currently fetches daily futures bars from
yfinance. Extend it:

```python
def get_ohlc(instrument, start_date, end_date, timeframe="daily", runner=None):
    """
    runner: 'ninjatrader' or 'mt5'
        If 'mt5' and the MT5 agent is reachable, fetch from MT5 directly
        (better data quality for FX).
        Otherwise fall back to yfinance.
    timeframe: 'daily' | 'H1' | 'H4'
    """
```

For forex strategies, the regime classifier needs H1 and H4. For futures
strategies, daily is still right.

Update the regime classification call in `backtest_runner.py`:

```python
if strategy.runner == "mt5":
    df_h1 = ohlc_fetcher.get_ohlc(instrument, ..., timeframe="H1", runner="mt5")
    df_h4 = ohlc_fetcher.get_ohlc(instrument, ..., timeframe="H4", runner="mt5")
    classify_regime(df_h1, df_h4)
else:
    df_daily = ohlc_fetcher.get_ohlc(instrument, ..., timeframe="daily", runner="ninjatrader")
    classify_regime(df_daily, df_daily)
```

### Strategy scanner update

The scanner currently looks at `strategies/ninjatrader/` for `.cs` files.
Add a parallel path for `strategies/mt5/` looking for `.mq5` files.

For MQL5 files, the scanner needs to read MQL5's `input` and `extern`
declarations to discover parameters — same idea as NinjaScript's
`[NinjaScriptProperty]`, different syntax.

MQL5 inputs are declared:
```mql5
input int LookbackPeriod = 20;    // Strategy logic param
input string Category_Risk_AccountSize = "Foundational";  // marker convention
```

For categorization, MQL5 doesn't have a `[Category]` attribute equivalent.
Two options:
- **Naming convention** — params named `f_AccountSize` (prefix `f_`) are
  foundational; others are strategy logic
- **Marker variables** — declare a const string above each input section
  indicating category

**Recommendation: naming convention.** Params with `f_` prefix are
foundational. Cleaner and works with MT5's parameter window naturally.
Document this convention in `strategies/CLAUDE.md`.

---

## 4. Frontend changes

### Runner badges on Strategies tab

Each strategy row gets a small badge next to its name:
- `NinjaTrader` — green pill `#10b981`
- `MT5` — blue pill `#3b82f6`

Reusable component `RunnerBadge.tsx`.

### Market filter across the lab

New filter at the top of:
- Strategies tab
- Runs tab (under Backtests)
- Sweeps tab
- Optimizations tab
- Stress Tests tab

Filter options: All / Futures / Forex.

Implementation: each strategy has `market` derived from its `runner`
(ninjatrader → futures, mt5 → forex). The filter applies to the
underlying data fetch, not just client-side filtering.

### Ruleset list

Existing ruleset_type badge is unchanged. Add a small market indicator
chip too — `FX` for forex rulesets, no chip for futures (they're the
default).

### Backtest Modal

When selecting a ruleset, the modal already enforces that
`strategy.allowed_instruments` matches the ruleset's allowed list. With
forex added, this same check just expands naturally.

The "Foundational Config" readonly section adapts to the runner — for
MT5 strategies, show spread instead of (or alongside) commission per
side. Pull from the new instrument_metadata table.

### Files / Deployed tab

The existing Deployed tab needs to know about both `.cs` and `.mq5`
files. Two ways to handle this:

- **A. Sub-tabs:** Deployed has its own internal toggle: NT8 / MT5
- **B. Unified view:** all deployed files in one list, with the runner
  shown per file

**Recommendation: B.** Same logic as the unified lab UI. One list with
labels. The file's location on the VPS (NT8's strategy folder vs MT5's
Experts folder) is determined by the file extension.

---

## 5. Pass 2 extensions for MT5

Pass 2 built the deployment manager for NT8. Extending it for MT5:

### Upload path

For a `.mq5` file: NT8 agent uploads to MT5's `MQL5/Experts/` folder
(typically `C:\Users\Administrator\AppData\Roaming\MetaQuotes\Terminal\
<terminal_id>\MQL5\Experts\`).

The exact path depends on the MT5 install. The mt5_agent should detect
it on startup via `mt5.terminal_info()` and document the path in
`backend/CLAUDE.md`.

### Compile

MT5 strategies are compiled by MetaEditor (the IDE that ships with MT5).
Two approaches:

**A. Command-line MetaEditor:**
```
metaeditor64.exe /compile:"<path to .mq5>" /log:<log_file>
```
Returns exit code 0 on success, non-zero on errors. Errors written to log.

**B. From Python via the `MetaTrader5` package:**
Less direct — there's no `compile()` function, but you can trigger a
"refresh" that picks up new files. Still requires MetaEditor.

**Recommendation: A.** Same model as NT8's NCompile.exe path (which
didn't exist in your install, so you fell back to F5). MetaEditor's CLI
is universally available with MT5.

### Lock detection

MT5 doesn't lock `.mq5` source files the way NT8 locks compiled .cs.
But it DOES lock the compiled `.ex5` file if a strategy is actively
running on a chart. The lock check is on the `.ex5`, not the `.mq5`.

Upload of `.mq5` is generally safe. Upload requires "stop running EA
first" warning only if the compiled .ex5 is in use.

---

## 6. Build order

Strict. Stop and report after each:

1. **MT5 agent skeleton.** `mt5_agent.py` on the VPS with just
   `/status`, `/historical_data`, and basic file listing. Smoke test:
   the Mac backend can connect to the MT5 agent over SSH tunnel and
   fetch H1 OHLC for EURUSD.

2. **Backend dispatcher refactor.** Move existing NT8 routing into a
   proper dispatcher. Add MT5 path. Smoke test: route a fake backtest
   request based on strategy.runner and verify it hits the right agent.

3. **Schema migrations.** Add `market` and `drawdown_unit` columns to
   rulesets. Create `instrument_metadata` table and seed it. Seed
   `personal_forex_main` and `personal_forex_demo`. Verify existing
   futures rulesets are unchanged.

4. **OHLC fetcher MT5 path.** Extend to fetch H1/H4 from MT5 agent.
   Test fetching EURUSD H1 for last 30 days, verify the data structure
   matches what regime classifier expects.

5. **Regime classification routing.** Update backtest_runner to call
   classifier with H1/H4 for MT5 strategies, daily for NT8. Smoke test:
   verify the regime tags get populated on a (still-fake) MT5 backtest
   result.

6. **Strategy scanner for .mq5.** Add the MQL5 parameter parsing.
   Apply naming convention for foundational params. Test on an empty
   `.mq5` file you create as a stub.

7. **MT5 Strategy Tester driver.** This is the heaviest single piece.
   The agent generates `.ini` configs, launches `terminal64.exe`,
   parses results. Get this working end-to-end with a stub strategy.

8. **Frontend — runner badges + market filter.** Add the visual
   distinction across all lab tabs.

9. **Deployment for MT5.** Extend Pass 2's deployment manager to
   handle `.mq5` files routing to MT5's Experts folder. Add the
   MetaEditor compile path.

10. **End-to-end test with the ported Mean Reversion strategy.**
    Once the separate Mean Reversion port is delivered, deploy it to
    MT5, run a backtest against `personal_forex_main`, verify the
    full pipeline (worthiness scoring, optimizer support, stress test,
    regime classification all work).

11. **Update CLAUDE.md.** Backend, frontend, design doc, plus
    `strategies/CLAUDE.md` (add MT5 conventions including the `f_`
    naming convention).

---

## 7. What NOT to do in M5

- Don't seed any forex prop firm rulesets. User trades personal funds
  for forex.
- Don't port the bot_smc_trend or bot_fft Python bots to MQL5. Only
  Mean Reversion in this milestone — the other two are deferred.
- Don't change the futures path. Existing NT8 lab behavior must stay
  bit-identical after the dispatcher refactor.
- Don't try to share code between the NT8 agent and MT5 agent — they
  live separately. The dispatcher is the only shared coordination point.
- Don't auto-detect broker suffix. Each instrument's `broker_suffix`
  field is set manually in `instrument_metadata`. User decides.
- Don't drive MT5 via pywinauto. Use the official Python library and
  command-line MetaEditor.
- Don't replace the regime classifier. Use the existing one — just call
  it with H1/H4 for forex.

---

## 8. CLAUDE.md updates

**backend/CLAUDE.md additions:**
- New services: `mt5_agent_client.py`
- Updated services: `nt8_agent_client.py` (renamed from `nt8_agent_client.py`),
  dispatcher in `nt8_agent_client.py` or new `agent_dispatcher.py`
- New tables: `instrument_metadata`
- Updated tables: `rulesets` (new `market` and `drawdown_unit` columns)
- Regime classification routing rule (H1/H4 for mt5, daily for
  ninjatrader)
- MT5 agent port (8766) and tunnel setup
- The MQL5 `f_` naming convention for foundational params

**frontend/CLAUDE.md additions:**
- `RunnerBadge` component
- Market filter (futures/forex/all) across lab tabs
- Unified Deployed tab handles both `.cs` and `.mq5`

**strategies/CLAUDE.md additions:**
- MT5 conventions: where files live, `f_` foundational naming, MQL5
  input declaration style, file extensions
- The mapping rules (which runner gets which timeframe for regime)

**Design doc:**
- M5 entry in §10 build order, marked COMPLETE with one-sentence
  summary
- Updated M1-M5 retrospective covering the dual-runner architecture
- A small architecture diagram (optional) showing the dispatcher
  routing strategies to one of two agents

---

## 9. After M5 ships

The lab now supports both futures and forex strategies. Pipeline is
identical for both — only the runner differs.

Next milestones:
- M6 — Strategy stacking / portfolio construction (waiting on at
  least 2 strategies grading B+ across either market)
- M7 — Dynamic risk allocation in stacking backtests
- M8 — Live deployment integration

Once M5 is shipped and validated end-to-end with the ported Mean
Reversion strategy, the user can write new MQL5 strategies and test
them through the same pipeline.

---

*End of M5 spec.*
