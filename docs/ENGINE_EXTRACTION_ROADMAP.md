# Engine Extraction Roadmap

**Purpose:** Track which parts of the TradingView SMC indicator still need to become their own Python engines.
**Source indicator:** `indicators/mpc_assistant.pine` (full-featured SMC: structure, order blocks, sessions, kill zones, VWAP, liquidity, fibs, SVP).
**Progress:** 7 SMC-port engines done (regime, market_structure, fibonacci, order_blocks, sessions, liquidity, vwap) · 1 to build (SVP) · **1 off-roadmap engine done (news / economic-calendar)** — see "Off-roadmap engines" below.
**Last reviewed:** 2026-07-05

---

## The pattern

Every engine is built the same way:

1. Port the Pine block line-by-line into a stateful streaming state machine (one closed bar in at a time).
2. Emit **events**, never visuals (e.g. "level touched", "block mitigated").
3. Validate at 100% Pine parity — instrument the Pine with `px_*` plot columns, export a CSV, diff Python-vs-Pine bar-by-bar with a `compare` tool.
4. Ship it as the single canonical implementation. Bots consume it through a thin `algos/shared/` shim.

Downstream engines (like the fibs) read another engine's **public output** only — never its internals.

---

## Done

- **`engines/regime/`** — market regime classifier (separate source, not the SMC indicator).
- **`engines/market_structure/`** — external + internal structure (BOS/CHoCH, swings, HH/HL/LH/LL). 100% Pine parity.
- **`engines/fibonacci/`** — Structure, Sniper, and Macro fibs. 100% Pine parity. Downstream of `engines/market_structure/`.
- **`engines/order_blocks/`** — bull/bear OB zones off external + internal breaks, with mitigation + FIFO eviction. Sibling of `engines/fibonacci/` (consumes `engines/market_structure/` directly). Ported line-by-line, 12 unit tests, 100% Pine parity on two independent real exports — `VANTAGE_XAUUSD, 5m` (`--warmup 594`) and `VANTAGE_XAUUSD, 15m` (`--warmup 207`), confirming it's timeframe-agnostic (harness: `indicators/ob_export.pine` + `engines/order_blocks/tools/compare_ob.py`).
- **`engines/sessions/`** — Tokyo/London/NY session windows + running session H/L, the three NY kill zones, and the NY opening range. The first **time-driven** engine (input = the bar's UTC timestamp + high/low, not just OHLC); standalone (depends on nothing). Ported line-by-line, 17 unit tests, **100% Pine parity** on a real `VANTAGE_XAUUSD, 5m` export (all 18 fields, `--warmup 263`), re-confirmed on a 15m export for the 16 timeframe-agnostic fields (harness: `indicators/sessions_export.pine` + `engines/sessions/tools/compare_sessions.py`). Unblocks the session-scoped parts of Liquidity (session H/L levels) and VWAP (session anchor).
- **`engines/liquidity/`** — the prices price runs toward and grabs: prev day/week/month H/L (PDH/PDL/PWH/PWL/PMH/PML), previous-week-close (PWC), the H4 sweep (SSH/BSL), and Asia/London/NY session H/L, with mitigation (sweep vs break) tracking. Consumes `engines/sessions/` for session H/L (composes it); reconstructs the day/week/month/H4 levels from the bar stream. **Non-repainting by Aaron's explicit decision (2026-07-05): every HTF level uses the PREVIOUS completed period only — the engine never forecasts the current period's high/low.** Ported, 15 unit tests, **100% Pine parity** on a real `VANTAGE_XAUUSD, 5m` export (11,457 bars; all 33 fields — 15 level prices, their mitigation flags, 4 boundary-roll pulses — match, `--htf-rollover 18 --warmup 4653`, exit 0; harness: `indicators/liquidity_export.pine` + `engines/liquidity/tools/compare_liquidity.py`). Calibrated boundary: XAUUSD session opens 18:00 NY (baked in as the default).
- **`engines/vwap/`** — the session VWAP: a volume-weighted running mean of `hlc3` (`ta.vwap(hlc3)`), re-anchored each trading day, plus a derived close-vs-line cross. First engine to need a **volume** column in the feed (XAUUSD tick volume — what the Pine `ta.vwap` already reads). Time-driven; reconstructs the trading-day anchor directly (the **same** 18:00-NY boundary the liquidity daily level uses), so it does not compose the sessions engine. Ported line-by-line from `mpc_assistant.pine` line 852, 13 unit tests, **100% Pine parity** on a real `VANTAGE_XAUUSD, 5m` export (6,973 bars; both fields — VWAP value + trading-day anchor pulse — match, `--htf-rollover 18 --warmup 90`, exit 0; harness: `indicators/vwap_export.pine` + `engines/vwap/tools/compare_vwap.py`). Uses a **relative** tolerance (1e-6) because the value is a cumulative sum that drifts at float-rounding level — unlike the copied-value level engines' exact match.

---

## Still to build — in priority order

### 1. Session Volume Profile (SVP)
- **What:** the Asia point-of-control / MV line.
- **Depends on:** `engines/sessions/` (now done); volume-heavy (uses the same volume feed VWAP just added).
- **Note:** niche — the last SMC-port engine.
- **Source block:** `SESSION VOLUME PROFILE` (~line 220, 2554).

---

## Off-roadmap engines (not from the SMC indicator)

These do not come from `mpc_assistant.pine`, so they follow the engine *shape* (time-driven,
streaming, events-not-visuals, `algos/shared/` shim) but **not** step 3 (Pine parity) — there is no
Pine source to diff against. Validated by unit tests + a live check instead.

- **`engines/news/`** — economic-calendar (news) engine. Built 2026-07-05. Turns each bar's UTC
  timestamp into a trade **blackout** around scheduled macro releases (NFP/CPI/FOMC/PCE/ISM/EIA…),
  plus **whole-day bank-holiday** blackouts (gold can't trade holidays; futures liquidity is thin),
  plus coming-up / happening-now / just-finished phases — so a bot can veto trading during news.
  Macro calendar keyed by currency → serves FX, gold and index/rates futures (not single-stock
  earnings). Two data paths, both into one local `EventStore` cache, behind a swappable
  `CalendarSource`: **live** = the free Forex Factory / faireconomy JSON feed (current week, no deps,
  `tools/refresh.py`); **history** = scrape the FF website month-by-month past Cloudflare via
  `curl_cffi` (`tools/backfill.py`) — cached, so static months are fetched once. Honest-coverage by
  Aaron's call (2026-07-05): before the cache's earliest fetched date the filter is inert (backtest
  trades normally) and the engine exposes `coverage_start_ms` for a UI "news starts here" line.
  29 unit tests + a live feed smoke + a real Feb-2025 backfill (blacked out ISM PMI + USD Presidents
  Day), green. Full rules in `engines/news/CLAUDE.md`.
  **Follow-up (not built):** wire `coverage_start_ms` into the command-center backtest lab as a
  vertical line; add the `algos/shared/` shim when a bot first consumes it.

## Suggested batch order

`SVP` (last one)

Sessions, Liquidity and VWAP are done. **SVP is the only SMC-port engine left** — the Asia
point-of-control / MV line, volume-heavy (it reuses the volume feed VWAP just introduced) and niche.
After SVP the extraction roadmap is complete.
