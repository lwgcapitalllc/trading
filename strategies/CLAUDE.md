# CLAUDE.md — Strategies

**Purpose:** Generic trading strategy implementations, organized by runner platform.
**Scope:** Strategy source files (`.cs` for NT8, `.mq5` for MT5, `.pine` for TradingView). Does NOT cover backtest infrastructure (see `command-center/`), live bot runtime logic (see `algos/`), or regime classification (see `regime/`).
**Status:** Production. NinjaTrader strategies are live and deployed via the command center. MT5 has two strategies (MeanReversion.mq5 smoke-tested, LondonBreakout.mq5). `tradingview/` holds Pine research strategies tested in the TradingView Strategy Tester only (NOT scanned/deployed by the command center). Tradovate is a placeholder.
**Last reviewed:** 2026-06-20

---

## Key paths

```
strategies/
├── ninjatrader/    ← NT8 NinjaScript strategies (.cs files, C#)
│   └── ORB.cs            (VWAP_MR.cs, Momentum.cs deleted 2026-06-21 — see below)
├── mt5/            ← MT5 expert advisors (.mq5, MQL5)
│   ├── MeanReversion.mq5
│   └── LondonBreakout.mq5
├── tradingview/    ← Pine v6 research strategies (.pine) — TV Strategy Tester only
│   ├── london_breakout.pine
│   └── ny_orb.pine
└── tradovate/      ← placeholder for future Tradovate strategies
```

`tradingview/` is research scratch space: hand-tested in the TradingView Strategy Tester, not picked up by the command-center scanner (which only rglobs `.cs` and `.mq5`). Promote a validated Pine idea by porting it to NT8/MT5.

---

## Standing instructions

**Do**
- Keep strategy logic generic — no firm-specific defaults baked in
- All foundational parameters (account size, daily loss, hours, commission, etc.) come from the active ruleset at runtime, injected by the command center dispatcher
- Use `[Category("Strategy Logic")]` on tunable parameters (visible to optimizer) and `[Category("Foundational")]` on injected parameters (hidden in UI)
- New strategies go in the appropriate runner subfolder
- After adding a strategy, run the scanner from the command center (`POST /strategies/scan`) to register it in the database

**Never do**
- Hardcode firm-specific values (account size, max daily loss, commission) as defaults in strategy files
- Name a strategy file with a firm name in it (`ORB_PropFirm.cs` is wrong — `ORB.cs` is right)
- Mix strategy trading logic with risk-management mechanics that belong in foundational config

---

## Adding a new NinjaTrader strategy

1. Create `<StrategyName>.cs` in `strategies/ninjatrader/`
2. Tag every `[NinjaScriptProperty]` with `[Category("Strategy Logic")]` or `[Category("Foundational")]`
3. Foundational params must default to sentinel values (e.g. -1 or empty string) so the strategy refuses to trade if injection fails
4. From the command center, click "Scan Strategies" to register it in the database
5. Click "Deploy" next to the strategy on the Strategies tab to upload to VPS
6. Click "Compile NT8" on the Deployed tab
7. Run a backtest to verify

## Adding a new MT5 strategy

1. Create `<StrategyName>.mq5` in `strategies/mt5/`
2. The strategy's class name must match the filename (MetaEditor requirement)
3. **Add the optimizer frame callbacks** (`OnTesterInit`/`OnTester`/`OnTesterPass`/`OnTesterDeinit`) if the strategy should be usable with the native MT5 optimizer. Without them single backtests and walk-forward work, but optimization runs every pass and harvests nothing — `opt_results.csv` is never written and the job fails with "OnTesterPass may not have fired". Copy the block from `MeanReversion.mq5` / `LondonBreakout.mq5`: `OnTesterInit` writes the header, `OnTester` `FrameAdd`s each combo's params + KPIs, `OnTesterPass` `FrameNext`s them into `opt_results.csv`. Column names must match the backend parser — KPI columns `net_pnl/profit_factor/max_drawdown/trade_count/win_trades/sharpe` (`gross_profit/gross_loss` optional) and param columns equal to the optimization grid keys.
4. From the command center, click "Scan Strategies" to register it in the database (scanner picks up `.mq5` via `strategies/mt5/` rglob)
5. Click "Deploy" next to the strategy on the Strategies tab — routes to the MT5 agent (port 8766) automatically based on `.mq5` extension
6. Click "Compile MT5" on the Deployed tab — compiles each `.mq5` explicitly (`metaeditor64.exe /compile:<file> /log`) and verifies success by the produced `.ex5` mtime advancing (MetaEditor's exit code is unreliable; the directory form `/compile:<dir>` could silently no-op and report a stale binary as success). A file whose `.ex5` mtime does not move is a hard failure with the compiler log surfaced — same mtime-polling check the NT8 agent uses on `NinjaTrader.Custom.dll`. The button only appears when MT5 files are present. **The VPS MT5 agent must be running the post-`509d16c` `mt5_agent.py` for this check to apply** — older deployed agents reported compile success without rebuilding; redeploy (`git pull` + agent restart) if `compiled_version` won't advance.
7. Run a backtest to verify (requires MT5 terminal running on VPS; strategy Tester ini+set approach)
8. **(Optional) Add a `<Strategy>.meta.json` next to the `.mq5`** to drive the friendly lab param editor (`ParamEditor`). It overlays editor metadata onto the scanned `param_schema`: per-param `label`, `desc`, `unit`, `group`, `core` (shown in the Essentials card), `widget` (`toggle`/`switch`/`time`), `options` `{off,on}` for bool toggles, `show_if` `{param: value}` for conditional visibility, `guide` `[lower, higher]`, and `step`. Param order in the file = UI order. Two **top-level** keys also drive the StrategyDetail overview: `edge` (one-paragraph "where the edge is") and `steps` (`[{label, title, detail}]` flow diagram). Both are optional and UI-only (stored on `strategies.edge`/`steps`); the page falls back to the editable description alone when absent. It affects the lab UI only — never the compiled `.ex5` or `source_hash`, so editing it needs no redeploy. The scanner re-reads it when its mtime is newer than the last scan, so **click Scan Strategies after editing it**. Missing meta = graceful fallback to the raw scanned schema. See `mt5/LondonBreakout.meta.json` for the reference.

---

## Current strategies

**Deleted 2026-06-21:** `VWAP_MR.cs` and `Momentum.cs`. They embedded their own
account-governance (daily-loss halt, profit-target stop, consecutive-loss halt, profit
lock-in) — risk management that now belongs in the dynamic sizing & gating engine, not the
strategy. Rather than refactor strategies that were against the gated-layer rules, they were
removed. `ORB.cs` is the one NT8 strategy carried forward and re-shaped to the engine. Any
lingering DB rows/runs clear on the next **Scan Strategies** (the scanner warns on a missing
`source_path`, never auto-deletes); remove the deployed `.cs` from the VPS via the Deployed tab.

| File | Class | Runner | Description |
|---|---|---|---|
| `ORB.cs` | ORB | ninjatrader | Opening Range Breakout — entry on ORB high/low break. The only live NT8 strategy. **Reshaped to the gated-layer rules 2026-06-21:** trades unit size (1 contract), self-policing halts removed (moved to the engine), keeps only signal + stop/target + time rules; emits the per-trade record to `engine_trades.csv` (the runner→engine contract). Needs VPS compile + backtest to verify. |
| `MeanReversion.mq5` | MeanReversion | mt5 | BB + RSI + intraday VWAP confluence — ported from `algos/bots/bot_mean_reversion.py` |
| `LondonBreakout.mq5` | LondonBreakout | mt5 | Asian-range (00:00–06:00 GMT) → London breakout, instrument-agnostic. v2 layers three default-OFF spec-faithful toggles (PendingEntry OCO, PipRangeFilter, BreakEvenMove) over the v1 bar-close/ATR/1:1 baseline; TargetRR default 2.0. Carries the `OnTester*` optimizer callbacks (writes the 5 strategy-logic params + 8 KPI columns to `opt_results.csv`). AUDJPY survivor config + per-toggle deltas in `mt5/LONDON_BREAKOUT.md`. |
| `ny_orb.pine` | — | tradingview | **In TradingView research/tuning (2026-06-20), not yet promoted.** NY Opening Range Breakout, instrument-agnostic (FX + futures). Built on `london_breakout.pine`'s skeleton. Range = wick-to-wick high/low of the opening window; sessions anchored to `America/New_York` (DST-safe). Entry = break candle (excluded from count) + N direction-filtered confirmation closes (`confirmCloses`, 0 = enter on the break candle itself; bullish closes for longs, bearish for shorts). Two entry methods: **Breakout Close** (market) and **Retest** (limit at the broken box edge). Far-side stop, RR target, optional partial + step-trail. Win/loss boxes recolour like London Breakout (no labels). Guards: forced `orderQty` (futures otherwise round to 0 contracts — see notes), weekend skip, and a volume-based thin/holiday-day filter (Pine has no calendar; OR volume < % of lookback average ⇒ skip). |

---

## Operational gap — NT8 auto-start on VPS reboot

NT8 does NOT need active RDP to keep running — strategies execute fine after disconnect. The gap is restarts: if the VPS reboots or NT8 crashes, nothing brings it back automatically.

MT5 bots use `SYS_STARTUP` (Windows scheduled task, "run whether logged on or not"). NT8 has no equivalent. Until it's built, a VPS reboot requires manual RDP to restart NT8 and reload strategies.

To fix: add a Windows scheduled task (trigger: At startup, run whether user is logged on or not) that launches NT8 and loads the active strategy set. Model it on `SYS_STARTUP` in `algos/`.

---

## TradingView (Pine) gotchas — learned on `ny_orb.pine`

- **No trades on futures = order-size/margin, not the script.** TV's Properties "order size" defaults to a cash/% value; one expensive futures contract (NQ ≈ $420k notional, MES ≈ $27k) divided by that rounds to **0 contracts**, or fails the 100% margin check against a small initial capital → every order rejected. FX fills because one unit is tiny. Fixes: pass an explicit `qty` (the script forces `orderQty`), set Properties order size to **Contracts**, raise initial capital, or lower margin %. Use the `SYMBOL1!` continuous contract (e.g. `MNQ1!`) and prefer micros for eval-sized accounts.
- **OR window ≠ chart timeframe.** A 15-min opening range on a 15-min chart is one candle and barely trades; run it on 1–5 min bars.
- **The volume thin/holiday filter is a backtest-only proxy.** Pine has no holiday/economic calendar. Live, the correct pattern is a shared calendar/event-gate service (like the regime classifier) that every bot checks before trading — it's proactive and also covers high-impact news (which is high-volume, so the volume filter misses it). Keep the volume proxy for TV research only.

## References

- `mt5/LONDON_BREAKOUT.md` — LondonBreakout design notes + v1 backtest record
- Build history (foundational config rules, NT8/MT5 deployment manager, this directory's creation) is in git history.
- `command-center/backend/CLAUDE.md` — scanner, deploy endpoint, sync-status logic, MT5 agent client
- `command-center/frontend/CLAUDE.md` — Strategies page, Deployed tab, Deploy button, MT5 compile button
- `algos/markets/fx/tools/mt5_agent.py` — MT5 agent on VPS (port 8766); owns the Experts folder write path
