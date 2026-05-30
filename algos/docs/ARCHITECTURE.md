# Multi-Instrument Architecture (Phases 1–5)

This document explains the shared scanner, risk, correlation, and learning-phase system that all four bots use. Bot guides reference this but don't repeat it.

---

## InstrumentScanner (`shared/shared_scanner.py`)

`InstrumentScanner.scan(detect_fn, watchlist=None)` iterates the watchlist, calls `detect_fn(symbol) → dict|None` per symbol, ranks by confluence score, returns sorted candidates. Optional `watchlist` param overrides `self.watchlist` for the call.

Each bot iterates candidates until one passes both the risk engine and correlation guard, then enters.

All MT5 methods accept `symbol=None` (defaults to bot's primary symbol). `move_sl`, `close_position`, `partial_close` read `pos[0].symbol` from the live MT5 position — instrument-agnostic. `close_all_positions(symbols=WATCHLIST)` covers all instruments in emergency closes.

Per-trade `symbol`, `atr`, and `lots` are stored in the trade dict at entry; position management uses them for correct trailing stop distances and risk engine calculations.

Unresolved watchlist symbols: WARNING log + `symbol_errors.log` + bot_state flag → monitor.py alert (once/day/symbol).

---

## Phase 2 — Volatility Filter

Before calling `detect_fn`, the scanner computes `atr_ratio = ATR(5) / ATR(20)` on H1 candles per symbol. Symbols below `min_atr_ratio` (default 0.8) are skipped. If the entire watchlist is below the floor and `force_trade=false`, the bot sits out the cycle.

Configured per bot in config.json: `"min_atr_ratio"` and `"force_trade"`.

---

## Phase 3 — Dynamic Risk Engine (`shared/shared_risk.py`)

`RiskEngine` tracks `available_risk = daily_budget − used_risk − realized_daily_loss`.

`used_risk` is computed from live MT5 SL positions each cycle — trades at breakeven contribute ~0; trades with SL trailing in profit contribute negative (locked gain frees capacity).

Before any new entry, each bot calls `risk_engine.evaluate(open_trades, balance, proposed_risk_pct)` which returns `(allowed, effective_risk_pct)`. Default `daily_budget_pct` equals each bot's existing daily loss cap, so day-one behaviour is identical to pre-Phase-3.

---

## Phase 4 — Correlation Control

After scanning, each bot iterates candidates in rank order and calls `corr_guard.check(symbol, open_trades, risk, action, balance)` before entering.

`CorrelationGuard` holds a static map of `{frozenset({sym1, sym2}): tier}` built from `correlation_map` in config.json. Only `"high"` tier triggers action:

- `correlation_action = "block"` (default): denies the candidate if any open position is high-correlated.
- `correlation_action = "shared_budget"`: allows it but caps proposed risk to the minimum live SL risk of any high-correlated open trade.

Bots loop to the next-ranked candidate before sitting out — a non-correlated setup on a different instrument is still taken.

---

## Phase 5 — AI Gate / Learning-Phase Cap (`shared/shared_scanner.py`)

`LearningPhaseGate` reads `ai.is_trained`. While untrained (< 15 win/loss trades, AUC < 0.55), the gate restricts each bot to `learning_watchlist` (2 instruments for FX bots, gold-only for FFT) and caps simultaneous open trades at `learning_max_open` (default 1).

Both limits lift automatically once the model deploys (`ai.is_trained = True`). No manual action required.

`InstrumentScanner.scan()` accepts an optional `watchlist` parameter so `LearningPhaseGate` can pass a per-call override without mutating the scanner's full watchlist.

Config per bot: `"learning_watchlist"` and `"learning_max_open"` in each bot's section of config.json.
