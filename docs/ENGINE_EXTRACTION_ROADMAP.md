# Engine Extraction Roadmap

**Purpose:** Track which parts of the TradingView SMC indicator still need to become their own Python engines.
**Source indicator:** `indicators/mpc_assistant.pine` (full-featured SMC: structure, order blocks, sessions, kill zones, VWAP, liquidity, fibs, SVP).
**Progress:** 5 engines done (regime, market_structure, fibonacci, order_blocks, sessions) · 3 to build (Liquidity, VWAP, SVP).
**Last reviewed:** 2026-07-04

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

---

## Still to build — in priority order

### 1. Liquidity levels
- **What:** the prices price runs toward and grabs — prev day/week/month highs and lows, previous-week-close, session highs and lows, H4 sweep (SSH/BSL), with mitigation tracking.
- **Depends on:** `engines/sessions/` for the session-H/L piece (now done — consume its `closed` SessionRange). The rest (day/week/month, PWC, H4) is standalone.
- **Emits:** level-created, level-swept.
- **Note:** biggest block of code (~400+ lines).
- **Source block:** `LIQUIDITY LEVELS` (~line 123) plus `DAILY / WEEKLY / MONTHLY LEVELS`, `PWC`, `H4 LIQUIDITY SWEEP`, `SESSION H/L` (~lines 1335–1762).

### 2. VWAP
- **What:** a session-anchored average line + cross events.
- **Depends on:** `engines/sessions/` for the anchor (now done); needs a **volume** column in the feed.
- **Emits:** VWAP value, VWAP cross.
- **Source block:** `VWAP` (~line 115).

### 3. Session Volume Profile (SVP)
- **What:** the Asia point-of-control / MV line.
- **Depends on:** `engines/sessions/` (now done); volume-heavy.
- **Note:** niche — do last.
- **Source block:** `SESSION VOLUME PROFILE` (~line 220, 2554).

---

## Suggested batch order

`Liquidity → VWAP → SVP`

Sessions is done, so its downstream dependants are unblocked. Liquidity is the highest-value
remaining engine; VWAP and SVP both also lean on `engines/sessions/`.

If building just one: **Liquidity** (highest value, and the session-H/L piece is now unblocked).
