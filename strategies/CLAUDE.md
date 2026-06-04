# CLAUDE.md — Strategies

**Purpose:** Generic trading strategy implementations, organized by runner platform.
**Scope:** Strategy source files (`.cs` for NT8, `.mq5` for MT5 when added). Does NOT cover backtest infrastructure (see `command-center/`), live bot runtime logic (see `algos/`), or regime classification (see `regime/`).
**Status:** Production. NinjaTrader strategies are live and deployed via the command center. MT5 and Tradovate are placeholders.
**Last reviewed:** 2026-06-04 (Pass 2.5 — moved from algos/markets/futures/lucid_flex/)

---

## Key paths

```
strategies/
├── ninjatrader/    ← NT8 NinjaScript strategies (.cs files, C#)
│   ├── ORB.cs
│   ├── VWAP_MR.cs
│   └── Momentum.cs
├── mt5/            ← MT5 expert advisors (.mq5, MQL5) — placeholder, no strategies yet
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
- Name a strategy file with a firm name in it (`ORB_LucidFlex.cs` is wrong — `ORB.cs` is right)
- Mix strategy trading logic with risk-management mechanics that belong in foundational config

---

## Adding a new NinjaTrader strategy

1. Create `<StrategyName>.cs` in `strategies/ninjatrader/`
2. Tag every `[NinjaScriptProperty]` with `[Category("Strategy Logic")]` or `[Category("Foundational")]`
3. Foundational params must default to sentinel values (e.g. -1 or empty string) so the strategy refuses to trade if injection fails
4. From the command center, click "Scan Strategies" to register it in the database
5. Click "Deploy" next to the strategy on the Strategies tab to upload to VPS
6. Click "Compile All" on the Deployed tab
7. Run a backtest to verify

---

## Current strategies

| File | Class | Runner | Description |
|---|---|---|---|
| `ORB.cs` | ORB | ninjatrader | Opening Range Breakout — entry on ORB high/low break |
| `VWAP_MR.cs` | VWAP_MR | ninjatrader | VWAP mean reversion — fades extended moves back to VWAP |
| `Momentum.cs` | Momentum | ninjatrader | EMA-based momentum — trend-following with MA crossover |

---

## References

- Pass 1 spec — foundational config rules and parameter categorization
- Pass 2 spec — VPS deployment manager (upload, compile, sync-status)
- Pass 2.5 spec — this directory's creation; moved from `algos/markets/futures/lucid_flex/`
- `command-center/backend/CLAUDE.md` — scanner, deploy endpoint, sync-status logic
- `command-center/frontend/CLAUDE.md` — Strategies page, Deployed tab, Deploy button
