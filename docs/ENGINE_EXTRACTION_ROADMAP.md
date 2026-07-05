# Engine Extraction Roadmap

**Purpose:** Track which parts of the TradingView SMC indicator still need to become their own Python engines.
**Source indicator:** `indicators/mpc_assistant.pine` (full-featured SMC: structure, order blocks, sessions, kill zones, VWAP, liquidity, fibs, SVP).
**Progress:** 6 engines done (regime, market_structure, fibonacci, order_blocks, sessions, liquidity) · 2 to build (VWAP, SVP).
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

---

## Still to build — in priority order

### 1. VWAP
- **What:** a session-anchored average line + cross events.
- **Depends on:** `engines/sessions/` for the anchor (now done); needs a **volume** column in the feed.
- **Emits:** VWAP value, VWAP cross.
- **Source block:** `VWAP` (~line 115).

### 2. Session Volume Profile (SVP)
- **What:** the Asia point-of-control / MV line.
- **Depends on:** `engines/sessions/` (now done); volume-heavy.
- **Note:** niche — do last.
- **Source block:** `SESSION VOLUME PROFILE` (~line 220, 2554).

---

## Suggested batch order

`VWAP → SVP`

Sessions and Liquidity are done. VWAP is next — it also leans on `engines/sessions/` (session
anchor) and needs a **volume** column in the feed. SVP (also volume-heavy, niche) is last.

If building just one: **VWAP** (session anchor is unblocked; more broadly useful than SVP).
