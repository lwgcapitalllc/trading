# Multi-Instrument Architecture (Phases 1–5)

> ## ⚠ HISTORICAL — this describes code that no longer exists
>
> **Every module named here was deleted on 2026-07-31 (commit `e92304a`)**, along with the four
> bots it was built for. This file is kept as a DESIGN RECORD, not as documentation of the
> current system: the reasoning is still worth reading, the file paths are not.
>
> Do not follow this document to find code. See [`DELETED_CODE.md`](DELETED_CODE.md) for what each
> module did and the one command that restores it.
>
> The live suite as of 2026-07-31 is `algos/live/` — one strategy, one symbol, one position at a
> time. Multi-instrument scanning, the risk engine and the correlation guard below are **not
> built** in it. The account-level allocator in particular is still an open prerequisite for
> running more than one bot (see the root `CLAUDE.md`), and `shared_risk.py` — described here — is
> the closest prior art.

This document explains the shared scanner, risk, correlation, and learning-phase system that the
four first-attempt bots used. Bot guides reference this but don't repeat it.

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

---

## Shared MT5 Architecture (BotMT5)

### BotMT5 class (`shared/mt5_ops.py`)

Encapsulates all MT5 operations for a single bot instance. Instantiate once at module level:

```python
_mt5 = BotMT5(SYMBOL, MAGIC, "BOT_NAME", _CFG, ACCOUNT, log)
```

Methods: `connect`, `get_candles`, `get_tick`, `place_order`, `move_sl`, `partial_close`,
`get_deal_result`, `close_position`, `close_all_positions`, `lot_size`,
`recover_open_positions`, `reconcile_on_startup`, `handle_dead_zone`.

Free functions (import directly): `now_utc`, `is_market_close`, `should_close_for_weekend`,
`is_dead_zone`, `get_atr`, `get_ema`.

### Thin delegate pattern

Each bot exposes module-level functions that forward to `_mt5`. Call sites stay unchanged:

```python
def connect():
    return _mt5.connect()


def get_candles(tf, n):
    return _mt5.get_candles(tf, n)


def get_tick():
    return _mt5.get_tick()


def get_deal_result(t):
    return _mt5.get_deal_result(t)


def close_position(t, d, r=""):
    return _mt5.close_position(t, d, r)


def close_all_positions(r="emergency"):
    return _mt5.close_all_positions(r)


def move_sl(t, sl, tp=None):
    return _mt5.move_sl(t, sl, tp)


def handle_dead_zone(ot, atr, logger, ai):
    return _mt5.handle_dead_zone(ot, atr, logger, ai)


def reconcile_on_startup(ot, logger, ai):
    return _mt5.reconcile_on_startup(ot, logger, ai)
```

### What stays bot-specific

- `lot_size` — wraps `_mt5.lot_size(balance, sl_dist, RISK_PCT, mult)` with bot's own RISK_PCT
- `place_order` — wraps `_mt5.place_order(...)` with bot-specific comment string
- `partial_close` — wraps `_mt5.partial_close(...)` (1-liner delegate)
- `recover_open_positions` — bot-specific if it needs extra trade dict fields (e.g., FFT's `fft_levels`)
- Strategy signals, regime logic, indicator calculations — never shared
- Bot-specific session/kill-zone helpers (e.g., `in_kill_zone`, `is_ny_session_close`)
