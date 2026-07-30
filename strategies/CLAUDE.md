# CLAUDE.md — Strategies

**Purpose:** Generic trading strategy implementations, organized by runner platform.
**Scope:** Strategy source files (`.cs` for NT8, `.mq5` for MT5, `.pine` for TradingView, Python packages for the local Python runner). Does NOT cover backtest infrastructure (see `command-center/` and top-level `backtest/`), live bot runtime logic (see `algos/`), or regime classification (see `engines/regime/`).
**Status:** Production. NT8 has one strategy (ORB.cs), deployed via the command center. MT5 has one strategy (LondonBreakout.mq5). Python has two strategies (`python/mpc_sos_fade/` and `python/mpc_bleg/`, run locally — no deploy). `tradingview/` holds Pine research strategies tested in the TradingView Strategy Tester only (NOT scanned/deployed by the command center).
**Last reviewed:** 2026-07-29 — **`mpc_sos_fade` Run 12: the A+ entry rule cannot be loosened for more trades, measured four ways over 6.5 years.** Dropping the FVG requirement adds 173 trades for +13.0R net on a 110.6R book while drawdown goes 54.9% → 77.1% (and 40% of the gross is ONE 2020 trade); sizing those extras at 5% instead of 10% is NEGATIVE (their benefit scales with size, the cost of displacing a real trade does not); deeper entries give FEWER trades AND less money; loosening which gaps qualify adds 65 trades and costs 32.4R, partly by RE-PRICING trades already taken. The final-hour rule costs ~0.4R over the same window, so it stays on. **The standing lesson for every strategy in this folder: with ONE position slot, a marginal setup is a queue, not an addition — trade count is a portfolio property, and sizing up a trusted book beats adding a marginal one** (shipped A+ at `exec_risk_pct=12.5` = 832x @ 64.2% DD vs 426x @ 64.9% for the loosened book). No strategy code changed; full record in `python/mpc_sos_fade/mpc_sos_fade_optimization.md` → Run 12 / 12b. Earlier the same day: **both parity gates re-run GREEN on fresh exports.** `compare_strategy.py` (A+, `VANTAGE_XAUUSD, 15_7b2f3.csv`, 21,494 bars, 2025-08-31 → 2026-07-29, at the shipped `exec_tp1_pct = exec_tp2_pct = 0`) and `compare_bleg.py` (B-LEG, `VANTAGE_XAUUSD, 15_ab202.csv`, 21,493 bars, same window) both exit 0 at `--warmup 100` and hold green at warmup 200/500/1000/2000, so the ~100-bar skip is genuine engine cold start, not a mask. Both Pine parents compile. Every "STALE" warning below is now CLEARED — the ratchet build is validated bar-for-bar on both forks. ⚠ One gap those runs do NOT cover: `mpc_strategy_export.pine` still lacks `execMinStopMode`/`execMinStopVal`, so A+ parity is proven only at the `"Off"` default. Earlier: 2026-07-28 — the **A+ runner trail defaults to `"Structure + % ratchet"`** (`exec_runner_trail` + the new `exec_trail_pct`, 1.0), shipped through `mpc_strategy.pine` → `mpc_strategy_export.pine` (`cfg_exitmode` 2-way → 3-way, new `cfg_trail_pct`) → `mpc_sos_fade` (`config.py`, `execution.py._trail`, `compare_strategy.py`, meta, 3 tests). It anchors on the last confirmed swing like the plain structure trail, then CLIMBS one %-of-price step per step of favourable move, so the runner stops handing back the gap to a lagging swing. ⚠ **A+ parity is STALE — the 2026-07-27 GREEN run predates this, so re-run `compare_strategy.py` on a fresh export before trusting any A+ number**, and run it at the shipped `exec_tp1_pct = exec_tp2_pct = 0`: the 109.3R figure in the ratchet write-up was measured at 1%/1%, and the true 0/0 baseline is **110.65R**. Same day, **extension fibs (negative fibs past 0.0) were measured and REJECTED in every form** — as shallow take-profit rungs (109.3R → 69.1R), as a stop floor that ratchets up the extension ladder (→ 56.1R, a fib line is a fixed price and does not breathe), and as deep rungs at −1/−4/−6 (Aaron's own hand ladder = 106.3R; the only rows that beat baseline sit at −6, which ONE trade in 6.6 years ever reached). Full record + the shape data behind it in `python/mpc_sos_fade/CLAUDE.md` → `### The swing ratchet`. Earlier the same day: the **B-LEG Pine pair caught up to the A+ exit ladder**: TP rungs 30/40 → **0/0**, the `qty_percent = 0` guard (without it a 0 rung closed the whole position at TP1), and the `"Structure + % ratchet"` runner trail + `execTrailPct`, now the default there too. `mpc_bleg/config.py` dropped its `exec_runner_trail` pin as a result. Both forks are back on ONE ladder; **the B-LEG export is stale until `compare_bleg.py` is re-run** (`cfg_exitmode`'s trail digit went 2-way → 3-way). Earlier: 2026-07-27 — the TP1/TP2 scale-out rungs default to **0/0** across both A+ Pine files and `config.py` (bank nothing, ride the runner — `mpc_sos_fade_optimization.md` Run 1 adopted), with a Pine-side guard because `strategy.exit(qty_percent = 0)` closes the WHOLE position; A+ parity re-validated GREEN at those defaults + SL fib 0.886. Earlier: 2026-07-26 — both Python bots gained the Pine's new exit levers (structure runner trail, TP2 stop floor), and the B-LEG's Pine-parity harness landed and went GREEN on its first real export; the switchable TP/SL register lives in `python/mpc_sos_fade/CLAUDE.md` → `## The exit ladder`

---

## Key paths

```
strategies/
├── ninjatrader/    ← NT8 NinjaScript strategies (.cs files, C#)
│   └── ORB.cs            (VWAP_MR.cs, Momentum.cs deleted 2026-06-21 — see below)
├── mt5/            ← MT5 expert advisors (.mq5, MQL5)
│   └── LondonBreakout.mq5
├── python/         ← Python strategy packages — run LOCALLY by the lab's python runner (no VPS)
│   ├── mpc_sos_fade/        (MPC SOS Fade bot; own CLAUDE.md inside)
│   └── mpc_bleg/            (MPC B-LEG bot — the late-retrace setup, split out to run parallel to A+; own CLAUDE.md)
└── tradingview/    ← Pine v6 research strategies (.pine) — TV Strategy Tester only
    ├── london_breakout.pine
    └── ny_orb.pine
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
3. **Add the optimizer frame callbacks** (`OnTesterInit`/`OnTester`/`OnTesterPass`/`OnTesterDeinit`) if the strategy should be usable with the native MT5 optimizer. Without them single backtests and walk-forward work, but optimization runs every pass and harvests nothing — `opt_results.csv` is never written and the job fails with "OnTesterPass may not have fired". Copy the block from `LondonBreakout.mq5`: `OnTesterInit` writes the header, `OnTester` `FrameAdd`s each combo's params + KPIs, `OnTesterPass` `FrameNext`s them into `opt_results.csv`. Column names must match the backend parser — KPI columns `net_pnl/profit_factor/max_drawdown/trade_count/win_trades/sharpe` (`gross_profit/gross_loss` optional) and param columns equal to the optimization grid keys.
4. From the command center, click "Scan Strategies" to register it in the database (scanner picks up `.mq5` via `strategies/mt5/` rglob)
5. Click "Deploy" next to the strategy on the Strategies tab — routes to the MT5 agent (port 8766) automatically based on `.mq5` extension
6. Click "Compile MT5" on the Deployed tab — compiles each `.mq5` explicitly (`metaeditor64.exe /compile:<file> /log`) and verifies success by the produced `.ex5` mtime advancing (MetaEditor's exit code is unreliable; the directory form `/compile:<dir>` could silently no-op and report a stale binary as success). A file whose `.ex5` mtime does not move is a hard failure with the compiler log surfaced — same mtime-polling check the NT8 agent uses on `NinjaTrader.Custom.dll`. The button only appears when MT5 files are present. **The VPS MT5 agent must be running the post-`509d16c` `mt5_agent.py` for this check to apply** — older deployed agents reported compile success without rebuilding; redeploy (`git pull` + agent restart) if `compiled_version` won't advance.
7. Run a backtest to verify (requires MT5 terminal running on VPS; strategy Tester ini+set approach)
8. **(Optional) Add a `<Strategy>.meta.json` next to the `.mq5`** to drive the friendly lab param editor (`ParamEditor`). It overlays editor metadata onto the scanned `param_schema`: per-param `label`, `desc`, `unit`, `group`, `core` (shown in the Essentials card), `widget` (`toggle`/`switch`/`time`), `options` `{off,on}` for bool toggles, `show_if` `{param: value}` for conditional visibility, `guide` `[lower, higher]`, `step`, and **`choices`** (a closed list of legal values for a string param → renders a DROPDOWN instead of a text box; use it for every enum, because strategies match enum strings exactly and silently no-op on anything else, so a typo disables the setting with no error). Param order in the file = UI order. Two **top-level** keys also drive the StrategyDetail overview: `edge` (one-paragraph "where the edge is") and `steps` (`[{label, title, detail}]` flow diagram). Both are optional and UI-only (stored on `strategies.edge`/`steps`); the page falls back to the editable description alone when absent. It affects the lab UI only — never the compiled `.ex5` or `source_hash`, so editing it needs no redeploy. The scanner re-reads it when its mtime is newer than the last scan, so **click Scan Strategies after editing it**. Missing meta = graceful fallback to the raw scanned schema. See `mt5/LondonBreakout.meta.json` for the reference.

## Adding a new Python strategy

1. Create a package `strategies/python/<name>/` with an `__init__.py` that declares `LAB_STRATEGY = {"strategy": <StrategyClass>, "config": <ConfigDataclass>, ...}` — declaring it is how a package opts in to the lab (see `python/mpc_sos_fade/__init__.py` for the reference).
2. The lab identifies the strategy by the **class's `__name__`** (stored as `class_name` by the scanner, sent as `strategy_class` in every job spec) — the package folder name is NOT the contract.
3. Click "Scan Strategies" to register it. No deploy, no compile — it runs in the backend process via the top-level `backtest/` package.
4. **Add `strategies/python/<name>/<name>.meta.json`** — same overlay the `.mq5` strategies use
   (`label`, `desc`, `unit`, `group`, `core`, `widget`, `options`, `show_if`, `guide`, `step`, plus
   top-level `edge`/`steps`). Without it the detail page is a bare list of raw field names in one
   "Strategy Logic" group. **Note the filename differs from the MT5 convention**: it is
   `<package>.meta.json` inside the package dir (`mpc_sos_fade/mpc_sos_fade.meta.json`), not
   `<ClassName>.meta.json`. UI-only, so editing it needs no re-parity — but re-scan after editing.
4. Strategy logic must consume the canonical `engines/` through `backtest/replay` — never a second engine implementation.
5. **Declare who sizes it.** Default (omit) = the strategy proposes UNIT-size trades and the lab's
   dynamic sizing engine sizes them per ruleset — the gated-layer rule that NT8/MT5 strategies
   follow. Add `"self_sizing": True` ONLY if the strategy computes its own position size from its
   own risk % (like `mpc_sos_fade`'s `exec_risk_pct`). It makes the lab leave the results alone;
   without it the engine re-sizes the run, throwing the strategy's real size away and leaving the
   KPI cards disagreeing with the equity chart. A self-sizing strategy's risk knob is a normal
   strategy param, so it stays editable per run and sweepable in the optimizer.

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
| `LondonBreakout.mq5` | LondonBreakout | mt5 | Asian-range → London breakout, instrument-agnostic. Reshaped to the gated-layer rules 2026-06-22 (v3). Needs VPS compile + backtest to verify — cannot be tested locally. See `mt5/LONDON_BREAKOUT.md` for design + reshape detail and backtest record. |
| `python/mpc_sos_fade/` | MpcSosFadeStrategy | python | MPC SOS Fade bot (XAUUSD 15m) — Python port of the brother's MPC-JARVIS A+ grade, replaying the canonical `engines/` via `backtest/`. **Logic-parity GREEN vs the Pine 2026-07-16** (bar-for-bar, exit 0). Runs locally in the lab (backtests + optimizer). **Parity RE-VALIDATED GREEN 2026-07-26** (exit 0) on a fresh 21,230-bar 15m export after the exit levers landed — the run caught an unpinned FVG engine input. **Re-validated again 2026-07-27** (exit 0, 21,320 bars) at the settings Aaron actually trades — SL fib 0.886 + the new 0/0 TP rungs — which was the first run of the whole-position-on-the-runner exit path against the Pine. Full rules in `python/mpc_sos_fade/CLAUDE.md`, exit levers in its `## The exit ladder` register. |
| `python/mpc_bleg/` | MpcBLegStrategy | python | MPC B-LEG bot (XAUUSD) — the late-retrace setup (the SOS whose retrace arrived late), split out of `mpc_strategy.pine` to run PARALLEL to A+ (2026-07-24). Port of `indicators/mpc_b_leg_strategy.pine`; REUSES `mpc_sos_fade`'s engine + A+ sequence + fill machinery, adds only the B-LEG tracker + a thin execution subclass. Built + 15 unit tests green. **Pine-parity GREEN (exit 0) 2026-07-26** on a real 21,231-bar 15m export — harness is `tools/compare_bleg.py` + `indicators/mpc_b_leg_strategy_export.pine`, wired into `verify_parity.py`. Only 5 trades in the window, so sample size (not correctness) is the open question. Full rules in `python/mpc_bleg/CLAUDE.md`. |
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
- **Pin `slippage = 0` AND `margin_long/short = 0.2` in the `strategy()` call, not the Properties UI.** The `.pine` strategy files (`mpc_strategy`, `mpc_strategy_export`, `mpc_b_leg_strategy`, `ny_orb`, `london_breakout`) declare `slippage = 0` (2026-07-23) and `margin_long = 0.2, margin_short = 0.2` (2026-07-24), so the Strategy Tester Properties tab defaults to zero slippage and 500x leverage (margin % = 100 / leverage) to match Aaron's demo account. Both are broker-emulator SETTINGS, not signal logic: TV slippage is a flat per-fill cost (in ticks; 25 ticks = $0.25 on gold) that is neither honest (a resting limit never slips) nor comparable to a zero-cost Python bar-mode run, and margin only sets the leverage the tester assumes. Model real costs in the LAB's tick fill model instead. The breakeven buffer is a strategy INPUT (signal logic), not a cost — leave it alone.

## References

- `mt5/LONDON_BREAKOUT.md` — LondonBreakout design notes, v3 reshape detail, and backtest record
- Build history (foundational config rules, NT8/MT5 deployment manager, this directory's creation) is in git history.
- `command-center/backend/CLAUDE.md` — scanner, deploy endpoint, sync-status logic, MT5 agent client
- `command-center/frontend/CLAUDE.md` — Strategies page, Deployed tab, Deploy button, MT5 compile button
- `algos/markets/fx/tools/mt5_agent.py` — MT5 agent on VPS (port 8766); owns the Experts folder write path
