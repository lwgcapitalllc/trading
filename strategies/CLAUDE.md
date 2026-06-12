# CLAUDE.md — Strategies

**Purpose:** Generic trading strategy implementations, organized by runner platform.
**Scope:** Strategy source files (`.cs` for NT8, `.mq5` for MT5). Does NOT cover backtest infrastructure (see `command-center/`), live bot runtime logic (see `algos/`), or regime classification (see `regime/`).
**Status:** Production. NinjaTrader strategies are live and deployed via the command center. MT5 has one strategy (MeanReversion.mq5, smoke-tested). Tradovate is a placeholder.
**Last reviewed:** 2026-06-12

---

## Key paths

```
strategies/
├── ninjatrader/    ← NT8 NinjaScript strategies (.cs files, C#)
│   ├── ORB.cs
│   ├── VWAP_MR.cs
│   └── Momentum.cs
├── mt5/            ← MT5 expert advisors (.mq5, MQL5)
│   └── MeanReversion.mq5
└── tradovate/      ← placeholder for future Tradovate strategies
```

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
3. From the command center, click "Scan Strategies" to register it in the database (scanner picks up `.mq5` via `strategies/mt5/` rglob)
4. Click "Deploy" next to the strategy on the Strategies tab — routes to the MT5 agent (port 8766) automatically based on `.mq5` extension
5. Click "Compile MT5" on the Deployed tab — runs `metaeditor64.exe /compile:<experts_dir>`; the button only appears when MT5 files are present
6. Run a backtest to verify (requires MT5 terminal running on VPS; strategy Tester ini+set approach)

---

## Current strategies

| File | Class | Runner | Description |
|---|---|---|---|
| `ORB.cs` | ORB | ninjatrader | Opening Range Breakout — entry on ORB high/low break |
| `VWAP_MR.cs` | VWAP_MR | ninjatrader | VWAP mean reversion — fades extended moves back to VWAP |
| `Momentum.cs` | Momentum | ninjatrader | EMA-based momentum — trend-following with MA crossover |
| `MeanReversion.mq5` | MeanReversion | mt5 | BB + RSI + intraday VWAP confluence — ported from `algos/bots/bot_mean_reversion.py` |

---

## Operational gap — NT8 auto-start on VPS reboot

NT8 does NOT need active RDP to keep running — strategies execute fine after disconnect. The gap is restarts: if the VPS reboots or NT8 crashes, nothing brings it back automatically.

MT5 bots use `SYS_STARTUP` (Windows scheduled task, "run whether logged on or not"). NT8 has no equivalent. Until it's built, a VPS reboot requires manual RDP to restart NT8 and reload strategies.

To fix: add a Windows scheduled task (trigger: At startup, run whether user is logged on or not) that launches NT8 and loads the active strategy set. Model it on `SYS_STARTUP` in `algos/`.

---

## References

- Pass 1 spec — foundational config rules and parameter categorization
- Pass 2 spec — VPS deployment manager (upload, compile, sync-status) for NT8
- Pass 2.5 spec — this directory's creation; moved from `algos/markets/futures/lucid_flex/`
- Step 9 — MT5 deployment manager (upload/delete `.mq5`, MetaEditor compile)
- `command-center/backend/CLAUDE.md` — scanner, deploy endpoint, sync-status logic, MT5 agent client
- `command-center/frontend/CLAUDE.md` — Strategies page, Deployed tab, Deploy button, MT5 compile button
- `algos/markets/fx/tools/mt5_agent.py` — MT5 agent on VPS (port 8766); owns the Experts folder write path
